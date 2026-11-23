"""Checks and the stage advance every applicant route module shares."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.dfa import InvalidTransitionError, build_transition_table
from app.domain.stage_requirements import StageRequirementsUnmetError
from app.models.candidate_application import CandidateApplication
from app.models.enums import StageType
from app.models.job_requisition import JobRequisition
from app.models.user import User
from app.schemas.applicant import ApplicationDetail
from app.services.applications import transition_application_stage

from .detail import to_detail


def own_application(db: Session, application_id: int, user: User) -> CandidateApplication:
    """The caller's own application, or a 404: someone else's application
    is never acknowledged to exist."""
    application = db.scalar(
        select(CandidateApplication).where(
            CandidateApplication.id == application_id,
            CandidateApplication.applicant_id == user.id,
        )
    )
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found")
    return application


def require_current_stage(application: CandidateApplication, expected: StageType) -> None:
    if application.current_stage != expected:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"This action is only available while the application is on '{expected.value}'.",
        )


def advance(
    db: Session, application: CandidateApplication, requisition: JobRequisition, payload: dict
) -> ApplicationDetail:
    """Moves the application to its next stage, writing `payload` onto the
    stage being completed, and commits. Every applicant submission advances
    through here (DFA, sufficiency gate, history row)."""
    next_stage = build_transition_table(requisition.workflow_definition).get(
        application.current_stage.value
    )
    if next_stage is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Already on the terminal stage.")
    try:
        transition_application_stage(
            db,
            application=application,
            requisition=requisition,
            target_stage=StageType(next_stage),
            triggered_by=str(application.applicant_id),
            current_stage_payload=payload,
        )
    except InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.reason) from exc
    except StageRequirementsUnmetError as exc:
        # no allow_incomplete override for applicants; the message names
        # the one thing they can act on, not internal keys
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=exc.missing[0].detail,
        ) from exc
    db.commit()
    db.refresh(application)
    return to_detail(db, application)
