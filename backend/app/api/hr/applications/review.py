"""HR reading applications: the pipeline list, the Candidate Profile,
resolving a Skill Matching flag, and rewriting the Decision Brief.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.hr.common import PIPELINE_ROLES
from app.domain.dfa import build_transition_table, InvalidTransitionError
from app.infra.db import get_db
from app.infra.deps import require_role
from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus, StageType
from app.models.job_requisition import JobRequisition
from app.models.user import User
from app.schemas.pipeline import ApplicationListItem, CandidateProfile, ResolveFlagRequest
from app.schemas.user import avatar_url
from app.services import offers
from app.services.applications import transition_application_stage
from app.services import shortlisting
from app.services.candidate_profile import build_candidate_profile, match_score_for
from app.services.decision_brief import BriefFacts, run_decision_brief
from app.services.jd_extraction import AIExtractionFailedError, ExtractionNotConfiguredError
from app.services.stage_labels import describe_transition_error, resolve_stage_label

router = APIRouter()


@router.get("/hr/applications", response_model=list[ApplicationListItem])
def list_applications(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> list[ApplicationListItem]:
    rows = db.execute(
        select(CandidateApplication, User.full_name, User.avatar_file, JobRequisition)
        .join(User, User.id == CandidateApplication.applicant_id)
        .join(JobRequisition, JobRequisition.id == CandidateApplication.requisition_id)
        .order_by(CandidateApplication.id)
    ).all()

    # expire overdue offers on read (see services.offers)
    if any(offers.expire_offer_if_overdue(db, application) for application, _, _, _ in rows):
        db.commit()

    items = []
    for application, applicant_name, applicant_avatar, requisition in rows:
        next_stage = None
        # a flagged application is frozen until resolve-flag: no next stage
        if application.current_stage is not None and application.status != ApplicationStatus.flagged:
            next_stage = build_transition_table(requisition.workflow_definition).get(
                application.current_stage.value
            )
        items.append(
            ApplicationListItem(
                id=application.id,
                applicant_name=applicant_name,
                applicant_avatar_url=avatar_url(applicant_avatar),
                job_title=requisition.title,
                requisition_id=requisition.id,
                current_stage=application.current_stage,
                current_stage_label=resolve_stage_label(
                    application.current_stage.value if application.current_stage else None,
                    requisition,
                ),
                next_stage=next_stage,
                status=application.status,
                match_score=match_score_for(db, application.id),
                shortlisting_outcome=shortlisting.read_outcome(db, application),
            )
        )
    return items


@router.get("/hr/applications/{application_id}/profile", response_model=CandidateProfile)
def get_candidate_profile(
    application_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> CandidateProfile:
    application = db.get(CandidateApplication, application_id)
    if application is not None and offers.expire_offer_if_overdue(db, application):
        db.commit()
    return build_candidate_profile(db, application_id)


@router.post(
    "/hr/applications/{application_id}/resolve-flag",
    response_model=CandidateProfile,
)
def resolve_flag(
    application_id: int,
    body: ResolveFlagRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> CandidateProfile:
    """HR's verdict on a Skill Matching flag (the agent never
    auto-rejects). 'reject' closes the application. 'continue' advances
    past skill_matching at once, keeping the stored analysis (no
    current_stage_payload is passed)."""
    application = db.get(CandidateApplication, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found")
    if application.status != ApplicationStatus.flagged:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="This application isn't currently flagged for review."
        )

    if body.decision == "reject":
        application.status = ApplicationStatus.rejected
        db.commit()
        return build_candidate_profile(db, application_id)

    requisition = db.get(JobRequisition, application.requisition_id)
    next_stage = build_transition_table(requisition.workflow_definition).get(
        application.current_stage.value
    )
    if next_stage is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Already on the terminal stage.")
    application.status = ApplicationStatus.active
    try:
        transition_application_stage(
            db,
            application=application,
            requisition=requisition,
            target_stage=StageType(next_stage),
            triggered_by=str(user.id),
        )
    except InvalidTransitionError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=describe_transition_error(exc, requisition),
        ) from exc
    db.commit()
    return build_candidate_profile(db, application_id)


@router.post(
    "/hr/applications/{application_id}/decision-brief",
    response_model=CandidateProfile,
)
def regenerate_decision_brief(
    application_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> CandidateProfile:
    """Rewrite the Decision Brief on demand.

    For a brief marked stale or never written (OpenAI unreachable).
    Unlike the automatic path, this reports a failure."""
    application = db.get(CandidateApplication, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found")

    synthesis = build_candidate_profile(db, application_id).synthesis
    try:
        run_decision_brief(
            db,
            application_id=application_id,
            stage_type=(
                application.current_stage.value if application.current_stage else "final_decision"
            ),
            facts=BriefFacts(
                lines=synthesis.fact_sheet, fingerprint=synthesis.fact_fingerprint
            ),
        )
    except ExtractionNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AIExtractionFailedError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    db.commit()

    return build_candidate_profile(db, application_id)
