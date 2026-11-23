"""Who evaluates whom: the evaluator account list, each job's evaluator
pool, per-candidate interview assignment, and reschedule requests.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.hr.common import PIPELINE_ROLES, ask_applicant_to_confirm_interview
from app.infra.db import get_db
from app.infra.deps import require_role
from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus, RescheduleRequestStatus, UserRole
from app.models.interview_reschedule_request import InterviewRescheduleRequest
from app.models.job_requisition import JobRequisition
from app.models.requisition_evaluator import RequisitionEvaluator
from app.models.stage_instance import StageInstance
from app.models.user import User
from app.schemas.pipeline import (
    CandidateProfile,
    EvaluatorAccountRead,
    InterviewAssignmentRequest,
    RequisitionEvaluatorAddRequest,
    RequisitionEvaluatorRead,
    RescheduleResolveRequest,
)
from app.schemas.user import avatar_url
from app.services import schedule_confirmation
from app.services.candidate_profile import build_candidate_profile
from app.services.notifications import notify
from app.services.stage_labels import resolve_stage_label

router = APIRouter(tags=["evaluators"])


@router.get("/hr/evaluators", response_model=list[EvaluatorAccountRead])
def list_evaluators(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> list[EvaluatorAccountRead]:
    # Switched-off accounts are left out: this list is what the Workflow
    # Builder offers for a job's pool, and an evaluator who can no longer
    # sign in could never conduct the interview they were added for.
    rows = db.scalars(
        select(User)
        .where(User.role == UserRole.evaluator, User.is_active.is_(True))
        .order_by(User.full_name)
    ).all()
    return [EvaluatorAccountRead.model_validate(u) for u in rows]


def _evaluator_has_conducted(db: Session, requisition_id: int, evaluator_id: int) -> bool:
    """Has this evaluator submitted a scorecard for any of this job's
    candidates (an `evaluation` on a stage assigned to them)?"""
    instances = db.scalars(
        select(StageInstance)
        .join(CandidateApplication, CandidateApplication.id == StageInstance.application_id)
        .where(
            CandidateApplication.requisition_id == requisition_id,
            StageInstance.assigned_evaluator_id == evaluator_id,
        )
    ).all()
    return any((instance.payload or {}).get("evaluation") for instance in instances)


def _requisition_evaluator_read(db: Session, row: RequisitionEvaluator) -> RequisitionEvaluatorRead:
    evaluator = db.get(User, row.evaluator_id)
    return RequisitionEvaluatorRead(
        id=row.id,
        evaluator_id=row.evaluator_id,
        full_name=evaluator.full_name,
        email=evaluator.email,
        avatar_url=avatar_url(evaluator.avatar_file),
        job_title=evaluator.job_title,
        department=evaluator.department,
        has_conducted=_evaluator_has_conducted(db, row.requisition_id, row.evaluator_id),
        is_active=evaluator.is_active,
    )


@router.get(
    "/hr/requisitions/{requisition_id}/evaluators", response_model=list[RequisitionEvaluatorRead]
)
def list_requisition_evaluators(
    requisition_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> list[RequisitionEvaluatorRead]:
    if db.get(JobRequisition, requisition_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Requisition not found")
    rows = db.scalars(
        select(RequisitionEvaluator).where(RequisitionEvaluator.requisition_id == requisition_id)
    ).all()
    return [_requisition_evaluator_read(db, row) for row in rows]


@router.post(
    "/hr/requisitions/{requisition_id}/evaluators",
    response_model=RequisitionEvaluatorRead,
    status_code=status.HTTP_201_CREATED,
)
def add_requisition_evaluator(
    requisition_id: int,
    body: RequisitionEvaluatorAddRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> RequisitionEvaluatorRead:
    if db.get(JobRequisition, requisition_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Requisition not found")
    evaluator = db.get(User, body.evaluator_id)
    if evaluator is None or evaluator.role != UserRole.evaluator:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Not a valid evaluator account.")
    if not evaluator.is_active:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="This evaluator's account is deactivated, so they can't conduct interviews.",
        )

    existing = db.scalar(
        select(RequisitionEvaluator).where(
            RequisitionEvaluator.requisition_id == requisition_id,
            RequisitionEvaluator.evaluator_id == body.evaluator_id,
        )
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This evaluator is already in the pool.")

    row = RequisitionEvaluator(requisition_id=requisition_id, evaluator_id=body.evaluator_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _requisition_evaluator_read(db, row)


@router.delete(
    "/hr/requisitions/{requisition_id}/evaluators/{evaluator_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_requisition_evaluator(
    requisition_id: int,
    evaluator_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> None:
    row = db.scalar(
        select(RequisitionEvaluator).where(
            RequisitionEvaluator.requisition_id == requisition_id,
            RequisitionEvaluator.evaluator_id == evaluator_id,
        )
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This evaluator isn't in the pool.")

    # blocked, not cascaded, while this evaluator is currently assigned
    # to an active application under this job -- shouldn't silently
    # orphan an in-flight interview assignment
    still_assigned = db.scalar(
        select(func.count())
        .select_from(StageInstance)
        .join(CandidateApplication, CandidateApplication.id == StageInstance.application_id)
        .where(
            CandidateApplication.requisition_id == requisition_id,
            CandidateApplication.status == ApplicationStatus.active,
            StageInstance.assigned_evaluator_id == evaluator_id,
        )
    )
    if still_assigned:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This evaluator is currently assigned to an active candidate's interview. Reassign it first.",
        )

    db.delete(row)
    db.commit()


@router.post("/hr/applications/{application_id}/interview-assignment", response_model=CandidateProfile)
def assign_interview_evaluator(
    application_id: int,
    body: InterviewAssignmentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> CandidateProfile:
    application = db.get(CandidateApplication, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found")

    instance = db.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application_id,
            StageInstance.stage_type == body.stage_type,
        )
    )
    if instance is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="This job's workflow has no such interview stage."
        )

    if body.evaluator_id is not None:
        in_pool = db.scalar(
            select(RequisitionEvaluator).where(
                RequisitionEvaluator.requisition_id == application.requisition_id,
                RequisitionEvaluator.evaluator_id == body.evaluator_id,
            )
        )
        if in_pool is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="This evaluator isn't in this job's evaluator pool.",
            )
        # a switched-off account stays in the pool but gets no new
        # interviews; unassigning and re-saving the current one are allowed
        evaluator = db.get(User, body.evaluator_id)
        if (
            evaluator is not None
            and not evaluator.is_active
            and body.evaluator_id != instance.assigned_evaluator_id
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="This evaluator's account is deactivated, so they can't conduct interviews.",
            )

    previously_assigned_id = instance.assigned_evaluator_id
    instance.assigned_evaluator_id = body.evaluator_id
    if body.evaluator_id is not None and body.evaluator_id != previously_assigned_id:
        requisition = db.get(JobRequisition, application.requisition_id)
        applicant = db.get(User, application.applicant_id)
        notify(
            db,
            kind="schedule",
            user_id=body.evaluator_id,
            actor_id=user.id,
            application_id=application.id,
            title="New interview assigned",
            message=(
                f"You've been assigned to conduct {resolve_stage_label(body.stage_type.value, requisition)} "
                f"for {applicant.full_name} ({requisition.title})."
            ),
            link=f"/evaluator/interviews/{instance.id}",
        )
    db.commit()
    return build_candidate_profile(db, application_id)


@router.post(
    "/hr/applications/{application_id}/reschedule-requests/{request_id}/resolve",
    response_model=CandidateProfile,
)
def resolve_reschedule_request(
    application_id: int,
    request_id: int,
    body: RescheduleResolveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> CandidateProfile:
    """Approve writes the evaluator's proposed time (or HR's own
    alternative, if they typed a different date/time) as the round's real
    schedule, asks the applicant to confirm it, and resolves the request.
    Deny just resolves it — the existing schedule, if any, is left
    untouched."""
    reschedule_request = db.get(InterviewRescheduleRequest, request_id)
    if reschedule_request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Reschedule request not found")
    if reschedule_request.status != RescheduleRequestStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This request has already been resolved.")

    instance = db.get(StageInstance, reschedule_request.stage_instance_id)
    if instance is None or instance.application_id != application_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Reschedule request not found")

    if body.decision == "approve":
        existing_schedule = (instance.payload or {}).get("schedule") or {}
        # a picked slot's end belonged to the old time, not this one
        schedule = {
            **{key: value for key, value in existing_schedule.items() if key != "end_time"},
            "date": body.date,
            "time": body.time,
        }
        instance.payload = {**(instance.payload or {}), "schedule": schedule}
        # A moved time is a new question: the
        # applicant is asked again, and told, in Set Schedule's words --
        # and the evaluator's form waits for the new answer.
        schedule_confirmation.open_confirmation(instance)
        application = db.get(CandidateApplication, application_id)
        ask_applicant_to_confirm_interview(
            db,
            application=application,
            requisition=db.get(JobRequisition, application.requisition_id),
            stage_type=instance.stage_type.value,
            schedule=schedule,
            actor=user,
        )
        reschedule_request.status = RescheduleRequestStatus.approved
        notify_title = "Reschedule approved"
        notify_message = f"HR approved your reschedule request. It's now set for {body.date} at {body.time}."
    else:
        reschedule_request.status = RescheduleRequestStatus.denied
        notify_title = "Reschedule denied"
        notify_message = "HR denied your reschedule request. The original schedule stands."

    reschedule_request.resolved_at = datetime.now(timezone.utc)
    reschedule_request.resolved_by = user.id
    notify(
        db,
        kind="schedule",
        user_id=reschedule_request.requested_by,
        actor_id=user.id,
        application_id=instance.application_id,
        title=notify_title,
        message=notify_message,
        link=f"/evaluator/interviews/{instance.id}",
    )
    db.commit()
    return build_candidate_profile(db, application_id)
