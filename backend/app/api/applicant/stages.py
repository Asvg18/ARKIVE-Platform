"""The applicant's own stage submissions: pre-screening, the onboarding
checklist, and answering a shortlisting.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infra.db import get_db
from app.infra.deps import require_role
from app.models.enums import ApplicationStatus, StageType, UserRole
from app.models.job_requisition import JobRequisition
from app.models.stage_instance import StageInstance
from app.models.user import User
from app.schemas.applicant import ApplicationDetail, OnboardingChecklistRequest, PreScreeningRequest
from app.schemas.skill_match import SkillMatchResult
from app.services import offers, shortlisting
from app.services.orchestration import run_pre_screening_pipeline
from app.services.resume_extraction import AIExtractionFailedError, ExtractionNotConfiguredError
from app.services.resume_profile import get_application_resume

from .common import advance, own_application, require_current_stage
from .detail import to_detail

router = APIRouter()


def _stored_skill_match(db: Session, application_id: int) -> SkillMatchResult | None:
    """The match stored at upload by documents._score_resume_against_job,
    so pre-screening reuses it instead of scoring again. None when there is
    nothing usable, which tells the pipeline to run the agent itself."""
    instance = db.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application_id,
            StageInstance.stage_type == StageType.skill_matching,
        )
    )
    if instance is None or not instance.payload:
        return None
    try:
        return SkillMatchResult.model_validate(instance.payload)
    except ValidationError:
        return None


@router.post(
    "/applicant/applications/{application_id}/pre-screening", response_model=ApplicationDetail
)
def submit_pre_screening(
    application_id: int,
    body: PreScreeningRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> ApplicationDetail:
    """Submit pre-screening answers and run the pre-screening agents
    (skill matching against the applied-to job, unless stored at upload).
    Above the flag threshold the application advances; below it, status
    becomes `flagged` and the DFA freezes at skill_matching until HR
    resolves it (POST /hr/applications/{id}/resolve-flag) -- a review gate,
    not an auto-rejection. Every required question must be answered."""
    application = own_application(db, application_id, user)
    require_current_stage(application, StageType.skill_matching)
    requisition = db.get(JobRequisition, application.requisition_id)
    resume = get_application_resume(db, application.id)
    if resume is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="A resume must be submitted before Pre-Screening.",
        )

    required_question_ids = {
        q["id"] for q in (requisition.pre_screening_questions or []) if q.get("required", True)
    }
    answered_ids = {a.question_id for a in body.answers if a.value.strip()}
    missing_questions = required_question_ids - answered_ids
    if missing_questions:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Every required question must be answered.",
        )

    # the agents run as a LangGraph StateGraph (orchestration.py); its
    # exceptions surface here. The match scored at upload is reused; when
    # there is none, the graph scores it itself.
    stored_match = _stored_skill_match(db, application.id)

    try:
        result = run_pre_screening_pipeline(
            db,
            application_id=application.id,
            requisition=requisition,
            resume=resume,
            answers=body.answers,
            match=stored_match,
        )
    except ExtractionNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AIExtractionFailedError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    match_result = result["match"]
    interview_analysis_result = result.get("analysis")

    payload = {
        "answers": [a.model_dump() for a in body.answers],
        **match_result.model_dump(),
        "interview_analysis": interview_analysis_result.model_dump() if interview_analysis_result else None,
    }

    if match_result.flagged:
        instance = db.scalar(
            select(StageInstance).where(
                StageInstance.application_id == application.id,
                StageInstance.stage_type == StageType.skill_matching,
            )
        )
        instance.payload = payload
        application.status = ApplicationStatus.flagged
        db.commit()
        db.refresh(application)
        return to_detail(db, application)

    return advance(db, application, requisition, payload)


@router.patch("/applicant/applications/{application_id}/onboarding", response_model=ApplicationDetail)
def submit_onboarding_checklist(
    application_id: int,
    body: OnboardingChecklistRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> ApplicationDetail:
    application = own_application(db, application_id, user)
    require_current_stage(application, StageType.onboarding)
    # an unanswered offer locks the checklist; a hire with no offer block
    # reads None and is unaffected
    offer = offers.read_offer(db, application)
    if offer is not None and offer.get("response") is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Respond to your offer before starting the onboarding checklist.",
        )
    instance = db.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.onboarding,
        )
    )
    instance.payload = {"checklist": body.checklist}
    db.commit()
    return to_detail(db, application)


@router.post(
    "/applicant/applications/{application_id}/shortlisting/accept",
    response_model=ApplicationDetail,
)
def accept_shortlisting(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> ApplicationDetail:
    """The shortlisted candidate confirms they still want the role, and is
    advanced through the same `advance` as every other applicant
    submission (DFA, sufficiency gate, history row)."""
    application = own_application(db, application_id, user)
    require_current_stage(application, StageType.shortlisting)
    requisition = db.get(JobRequisition, application.requisition_id)
    try:
        shortlisting.respond(db, application, response=shortlisting.ACCEPTED)
    except shortlisting.ShortlistingUnavailableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    instance = shortlisting.shortlisting_instance(db, application)
    return advance(db, application, requisition, instance.payload or {})


@router.post(
    "/applicant/applications/{application_id}/shortlisting/decline",
    response_model=ApplicationDetail,
)
def decline_shortlisting(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> ApplicationDetail:
    """The shortlisted candidate declines: the application is withdrawn,
    as with Cancel Application. There is no undo."""
    application = own_application(db, application_id, user)
    require_current_stage(application, StageType.shortlisting)
    try:
        shortlisting.respond(db, application, response=shortlisting.DECLINED)
    except shortlisting.ShortlistingUnavailableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return to_detail(db, application)
