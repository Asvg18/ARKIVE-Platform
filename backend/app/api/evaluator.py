"""Evaluator-facing routes, scoped by assignment
(StageInstance.assigned_evaluator_id): an evaluator sees exactly the
interview rounds HR assigned them, nothing more.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infra.db import get_db
from app.infra.deps import require_role
from app.domain.interview_slots import round_duration, to_minutes
from app.domain.scorecard import compute_score, compute_tier
from app.models.candidate_application import CandidateApplication
from app.models.enums import RescheduleRequestStatus, StageStatus, UserRole
from app.models.interview_availability import InterviewAvailability
from app.models.interview_reschedule_request import InterviewRescheduleRequest
from app.models.job_requisition import JobRequisition
from app.models.stage_instance import StageInstance
from app.models.user import User
from app.schemas.evaluator import (
    AvailabilityUpdateRequest,
    AvailabilityWindowRead,
    EvaluationRequest,
    InterviewDetail,
    InterviewListItem,
    RescheduleRequestCreate,
    RescheduleRequestRead,
)
from app.schemas.user import avatar_url
# the Decision Brief's facts are built in one place, shared with HR's
# read path
from app.services.candidate_profile import refresh_decision_brief
from app.services import interview_scheduling, schedule_confirmation
from app.services.agents import EVALUATOR_SCORECARD
from app.services.file_storage import resolve_resume_path
from app.services.interview_synthesis import (
    AIExtractionFailedError,
    ExtractionNotConfiguredError,
    run_interview_synthesis,
)
from app.services.notifications import notify
from app.services.resume_profile import get_application_resume, to_resume_read
from app.services.stage_labels import resolve_stage_label

router = APIRouter(prefix="/evaluator", tags=["evaluator"])


def _own_interview(db: Session, stage_instance_id: int, user: User) -> StageInstance:
    instance = db.scalar(
        select(StageInstance).where(
            StageInstance.id == stage_instance_id,
            StageInstance.assigned_evaluator_id == user.id,
        )
    )
    if instance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Interview not found")
    return instance


def _pending_reschedule_request(db: Session, stage_instance_id: int) -> InterviewRescheduleRequest | None:
    return db.scalar(
        select(InterviewRescheduleRequest).where(
            InterviewRescheduleRequest.stage_instance_id == stage_instance_id,
            InterviewRescheduleRequest.status == RescheduleRequestStatus.pending,
        )
    )


@router.get("/interviews", response_model=list[InterviewListItem])
def list_my_interviews(
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.evaluator)),
) -> list[InterviewListItem]:
    # every interview assigned to this evaluator, whatever its status,
    # including `pending` rounds the candidate hasn't reached: they are
    # notified on assignment, so the queue must show them (as upcoming;
    # submit_evaluation refuses them)
    rows = db.execute(
        select(StageInstance, CandidateApplication, User.full_name, User.avatar_file, JobRequisition)
        .join(CandidateApplication, CandidateApplication.id == StageInstance.application_id)
        .join(User, User.id == CandidateApplication.applicant_id)
        .join(JobRequisition, JobRequisition.id == CandidateApplication.requisition_id)
        .where(StageInstance.assigned_evaluator_id == user.id)
        .order_by(StageInstance.id)
    ).all()

    return [
        InterviewListItem(
            stage_instance_id=instance.id,
            application_id=application.id,
            applicant_name=applicant_name,
            applicant_avatar_url=avatar_url(applicant_avatar),
            job_title=requisition.title,
            stage_label=resolve_stage_label(instance.stage_type.value, requisition),
            status=instance.status.value,
            already_evaluated=bool((instance.payload or {}).get("evaluation")),
            schedule_confirmed=schedule_confirmation.time_confirmed(instance),
        )
        for instance, application, applicant_name, applicant_avatar, requisition in rows
    ]


@router.get("/interviews/{stage_instance_id}", response_model=InterviewDetail)
def get_interview_detail(
    stage_instance_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.evaluator)),
) -> InterviewDetail:
    instance = _own_interview(db, stage_instance_id, user)
    application = db.get(CandidateApplication, instance.application_id)
    requisition = db.get(JobRequisition, application.requisition_id)
    applicant = db.get(User, application.applicant_id)

    # Only the resume itself -- the AI's match score and top skills are
    # never sent to evaluators, so their judgement stays independent of it.
    resume = to_resume_read(get_application_resume(db, application.id))

    payload = instance.payload or {}
    pending_request = _pending_reschedule_request(db, instance.id)
    offer = interview_scheduling.read_offer(instance)
    return InterviewDetail(
        stage_instance_id=instance.id,
        application_id=application.id,
        applicant_name=applicant.full_name,
        applicant_avatar_url=avatar_url(applicant.avatar_file),
        job_title=requisition.title,
        stage_type=instance.stage_type.value,
        stage_label=resolve_stage_label(instance.stage_type.value, requisition),
        status=instance.status.value,
        resume=resume,
        schedule=payload.get("schedule"),
        evaluation=payload.get("evaluation"),
        pending_reschedule_request=(
            RescheduleRequestRead.model_validate(pending_request, from_attributes=True)
            if pending_request
            else None
        ),
        availability=[
            AvailabilityWindowRead(date=row.date, start=row.start_time, end=row.end_time)
            for row in interview_scheduling.availability_windows(db, instance)
        ],
        duration_minutes=round_duration(instance.stage_type.value, requisition.interview_durations),
        times_sent=offer is not None and offer.get("response") is None and not payload.get("schedule"),
        schedule_confirmed=schedule_confirmation.time_confirmed(instance),
    )


@router.get("/applications/{application_id}/resume-file")
def download_resume_file_for_evaluator(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.evaluator)),
) -> FileResponse:
    """Scoped like the rest of this router -- an evaluator can only
    reach a resume for an application with an interview instance
    specifically assigned to them, never any application by raw id."""
    instance = db.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application_id,
            StageInstance.assigned_evaluator_id == user.id,
        )
    )
    if instance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Interview not found")

    resume = get_application_resume(db, application_id)
    if resume is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No resume uploaded yet.")
    path = resolve_resume_path(resume.stored_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resume file is missing.")
    return FileResponse(path, media_type="application/pdf", filename=resume.original_filename)


@router.post("/interviews/{stage_instance_id}/evaluate", response_model=InterviewDetail)
def submit_evaluation(
    stage_instance_id: int,
    body: EvaluationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.evaluator)),
) -> InterviewDetail:
    """Record the signed-in evaluator's scorecard for their own interview
    (404 for an interview that is not theirs).

    Refused (409) while the round is pending, once already submitted, or
    before the applicant has confirmed the interview time. The score and
    tier are computed here from the ratings, never taken from the client;
    the interview synthesis agent adds its summary (503 without an OpenAI
    key, 502 on a model failure). Commits, then refreshes the Decision
    Brief in a second commit so an AI failure there cannot lose the
    scorecard."""
    instance = _own_interview(db, stage_instance_id, user)
    # A round the candidate hasn't reached can't be evaluated. The page
    # shows the form read-only, but the notification links straight
    # here, so the rule has to hold on the server.
    if instance.status == StageStatus.pending:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                "This candidate hasn't reached this interview round yet. "
                "You'll be able to record your evaluation once they do."
            ),
        )
    payload = instance.payload or {}
    # locked after submission -- edits would go through a separate
    # logged "revise" action, out of scope here
    if payload.get("evaluation"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="This evaluation has already been submitted."
        )
    # Nobody has agreed to this interview time yet, so there is nothing
    # to have scored. The page shows the form disabled; this makes it a
    # rule.
    if not schedule_confirmation.time_confirmed(instance):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                "Waiting for schedule. The form opens once the applicant has "
                "confirmed the interview time."
            ),
        )

    # computed here, never taken from the client, so a scorecard always
    # matches its own ratings
    computed_score = compute_score(body.item_ratings)
    tier = compute_tier(computed_score)
    try:
        analysis = run_interview_synthesis(
            db,
            application_id=instance.application_id,
            stage_type=instance.stage_type.value,
            item_ratings=body.item_ratings,
            remarks=body.remarks,
        )
    except ExtractionNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AIExtractionFailedError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    evaluation = {
        "item_ratings": body.item_ratings,
        "computed_score": computed_score,
        "tier": tier,
        # stored beside the derived tier, never instead of it -- tier is
        # what the ratings add up to, this is what the interviewer
        # actually concluded. keeping both keeps a disagreement visible.
        "recommendation": body.recommendation,
        "remarks": body.remarks,
        "ai_summary": analysis.summary,
        "rubric_coverage_score": analysis.rubric_coverage_score,
        "submitted_by": user.id,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    # a fresh dict, not a mutation: the JSON column has no mutation
    # tracking, so an in-place change would never be saved
    instance.payload = {**payload, "evaluation": evaluation}

    # deterministic, non-LLM computation logged to the same AgentRun
    # trail as exam_scheduling_agent -- AgentRun isn't reserved for
    # LLM-based agents only
    EVALUATOR_SCORECARD.log(
        db,
        application_id=instance.application_id,
        triggered_by_stage=instance.stage_type.value,
        output={
            "item_ratings": body.item_ratings,
            "computed_score": computed_score,
            "tier": tier,
            "recommendation": body.recommendation,
        },
    )

    db.commit()

    # after the commit, so an OpenAI outage can never lose the scorecard
    if refresh_decision_brief(db, instance.application_id, stage_type=instance.stage_type.value):
        db.commit()

    return get_interview_detail(stage_instance_id, db=db, user=user)


@router.post(
    "/interviews/{stage_instance_id}/reschedule-request",
    response_model=InterviewDetail,
    status_code=status.HTTP_201_CREATED,
)
def request_reschedule(
    stage_instance_id: int,
    body: RescheduleRequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.evaluator)),
) -> InterviewDetail:
    """The assigned evaluator proposes a new time for a round they can't
    make -- HR reviews and resolves it from the Candidate Profile page."""
    instance = _own_interview(db, stage_instance_id, user)
    payload = instance.payload or {}
    if payload.get("evaluation"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="This interview has already been evaluated."
        )
    if _pending_reschedule_request(db, stage_instance_id) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="A reschedule request is already pending for this round."
        )

    db.add(
        InterviewRescheduleRequest(
            stage_instance_id=stage_instance_id,
            requested_by=user.id,
            proposed_date=body.proposed_date,
            proposed_time=body.proposed_time,
            reason=body.reason,
        )
    )

    application = db.get(CandidateApplication, instance.application_id)
    applicant = db.get(User, application.applicant_id)
    # notifies every HR admin instead of tracking a single "owner" per
    # job -- simpler for a small team where any admin might act on it
    for hr_admin in db.scalars(select(User).where(User.role == UserRole.hr_admin)):
        notify(
            db,
            kind="schedule",
            user_id=hr_admin.id,
            actor_id=user.id,
            application_id=application.id,
            title="Reschedule request",
            message=(
                f"{user.full_name} requested to reschedule {applicant.full_name}'s "
                f"{resolve_stage_label(instance.stage_type.value, db.get(JobRequisition, application.requisition_id))} "
                f"to {body.proposed_date} at {body.proposed_time}."
            ),
            link=f"/hr/applications/{application.id}",
        )

    db.commit()

    return get_interview_detail(stage_instance_id, db=db, user=user)


@router.put("/interviews/{stage_instance_id}/availability", response_model=InterviewDetail)
def save_availability(
    stage_instance_id: int,
    body: AvailabilityUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.evaluator)),
) -> InterviewDetail:
    """The ranges this evaluator is free in for this round; replaces the
    whole set. HR cuts them into slots of the round's length and sends
    some to the applicant. Open from assignment, before the candidate
    reaches the round."""
    instance = _own_interview(db, stage_instance_id, user)
    if (instance.payload or {}).get("evaluation"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="This interview has already been evaluated."
        )
    application = db.get(CandidateApplication, instance.application_id)
    requisition = db.get(JobRequisition, application.requisition_id)
    minutes = round_duration(instance.stage_type.value, requisition.interview_durations)
    for window in body.windows:
        if to_minutes(window.end) - to_minutes(window.start) < minutes:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Each range has to be at least {minutes} minutes, the length of this interview.",
            )

    for row in db.scalars(
        select(InterviewAvailability).where(
            InterviewAvailability.stage_instance_id == instance.id,
            InterviewAvailability.evaluator_id == user.id,
        )
    ):
        db.delete(row)
    for window in body.windows:
        db.add(
            InterviewAvailability(
                stage_instance_id=instance.id,
                evaluator_id=user.id,
                date=window.date,
                start_time=window.start,
                end_time=window.end,
            )
        )

    if body.windows:
        applicant = db.get(User, application.applicant_id)
        stage_label = resolve_stage_label(instance.stage_type.value, requisition)
        # every HR admin, same as the reschedule request -- any of them
        # may be the one who sends the times on
        for hr_admin in db.scalars(select(User).where(User.role == UserRole.hr_admin)):
            notify(
                db,
                kind="schedule",
                user_id=hr_admin.id,
                actor_id=user.id,
                application_id=application.id,
                title="Free times added",
                message=(
                    f"{user.full_name} added their free times for {applicant.full_name}'s "
                    f"{stage_label}, ready to send to the applicant."
                ),
                link=f"/hr/applications/{application.id}",
            )
    db.commit()
    return get_interview_detail(stage_instance_id, db=db, user=user)
