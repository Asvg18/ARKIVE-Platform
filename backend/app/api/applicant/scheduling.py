"""Scheduling, from the applicant's side: confirming an interview time,
booking an exam session, and picking from the interview times HR sent.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.dfa import is_interview_stage
from app.domain.schedule_time import format_session
from app.infra.db import get_db
from app.infra.deps import require_role
from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus, StageType, UserRole
from app.models.exam_slot import ExamSlot
from app.models.job_requisition import JobRequisition
from app.models.stage_instance import StageInstance
from app.models.user import User
from app.schemas.applicant import (
    ApplicationDetail,
    ExamBookingRequest,
    ExamNoneWorkRequest,
    InterviewSlotDeclineRequest,
    InterviewSlotPickRequest,
    ScheduleConfirmationRequest,
)
from app.services import exam_scheduling, interview_scheduling, schedule_confirmation
from app.services.email import send_email_safely
from app.services.notifications import notify
from app.services.stage_labels import resolve_stage_label

from .common import own_application, require_current_stage
from .detail import to_detail

router = APIRouter()


@router.post(
    "/applicant/applications/{application_id}/schedule-confirmation",
    response_model=ApplicationDetail,
)
def confirm_schedule(
    application_id: int,
    body: ScheduleConfirmationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> ApplicationDetail:
    """Answers "can you make this time?" for a scheduled interview.

    Saying no does NOT withdraw the application: it records the clash and
    the candidate's note, and tells HR, who rearrange.

    No require_current_stage: HR can schedule a round the applicant has
    not reached yet. Ownership is checked, and the stage must be scheduled
    and asking.
    """
    application = own_application(db, application_id, user)
    if not is_interview_stage(body.stage_type.value):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only interview stages ask for a scheduling confirmation.",
        )

    instance = db.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == body.stage_type,
        )
    )
    if instance is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="This application has no such interview stage."
        )

    schedule = (instance.payload or {}).get("schedule") or {}
    try:
        schedule_confirmation.respond(
            db, instance=instance, response=body.response, note=body.note
        )
    except schedule_confirmation.ScheduleConfirmationUnavailableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if body.response == schedule_confirmation.UNAVAILABLE:
        # every HR admin is told; any of them may be the one to rearrange
        requisition = db.get(JobRequisition, application.requisition_id)
        stage_label = resolve_stage_label(body.stage_type.value, requisition)
        said = body.note.strip()
        detail = f': "{said}"' if said else '.'
        for hr_admin in db.scalars(select(User).where(User.role == UserRole.hr_admin)):
            notify(
                db,
                kind="schedule",
                user_id=hr_admin.id,
                actor_id=user.id,
                application_id=application.id,
                title="Applicant can't attend",
                message=(
                    f"{user.full_name} is not available for their {stage_label} on "
                    f"{schedule.get('date', 'the scheduled date')}{detail}"
                ),
                link=f"/hr/applications/{application.id}",
            )

    db.commit()
    return to_detail(db, application)


def _exam_stage_instance(db: Session, application: CandidateApplication, stage_type: StageType) -> StageInstance:
    """The applicant's own exam stage they're on, for the booking routes."""
    if application.status != ApplicationStatus.active:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Only an active application can book an examination."
        )
    require_current_stage(application, stage_type)
    instance = db.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == stage_type,
        )
    )
    if instance is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="This application has no such examination stage."
        )
    return instance


def _book(
    db: Session,
    *,
    user: User,
    application: CandidateApplication,
    instance: StageInstance,
    exam_slot_id: int,
    changing: bool,
) -> ApplicationDetail:
    """Books (or changes to) one of the job's sessions for the applicant
    and tells them, on both channels, the same way HR's booking does."""
    requisition = db.get(JobRequisition, application.requisition_id)
    slot = db.get(ExamSlot, exam_slot_id)
    if slot is None or slot.requisition_id != requisition.id or slot.stage_type != instance.stage_type.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Exam session not found.")

    try:
        exam_scheduling.book_session(db, instance=instance, exam_slot_id=slot.id, enforce_cutoff=True)
    except (
        exam_scheduling.ExamSessionFullError,
        exam_scheduling.ExamChangeClosedError,
        exam_scheduling.ExamSessionUnchangedError,
    ) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    stage_label = resolve_stage_label(instance.stage_type.value, requisition)
    when = format_session(slot.date, slot.time, slot.end_time)
    notify(
        db,
        kind="schedule",
        user_id=user.id,
        actor_id=None,
        application_id=application.id,
        title=f"Your {stage_label} is booked",
        message=f"Your {stage_label} is {'now ' if changing else ''}booked for {when}, at {slot.location}.",
        link=f"/applicant/applications/{application.id}",
    )
    send_email_safely(
        to=user.email,
        subject=f"Your {stage_label} is booked: {requisition.title}",
        body=(
            f"Hi {user.full_name},\n\n"
            f"Your {stage_label} for {requisition.title} is {'now ' if changing else ''}booked:\n\n"
            f"  When: {when}\n"
            f"  Where: {slot.location}\n\n"
            "You can change it on your application page until 24 hours before it starts. "
            "After that, contact the HR office.\n"
        ),
    )
    db.commit()
    return to_detail(db, application)


@router.post(
    "/applicant/applications/{application_id}/exam-booking",
    response_model=ApplicationDetail,
)
def book_exam_session(
    application_id: int,
    body: ExamBookingRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> ApplicationDetail:
    """The applicant books one of the job's exam sessions with a free
    seat, on the exam stage they are on. Booked at once (the seat limit
    keeps it fair, so no HR approval) and written onto the stage as its
    schedule. Changing it is the PUT below."""
    application = own_application(db, application_id, user)
    instance = _exam_stage_instance(db, application, body.stage_type)
    if (instance.payload or {}).get("schedule"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Your examination is already booked. Use Change Session to pick another.",
        )
    return _book(db, user=user, application=application, instance=instance, exam_slot_id=body.exam_slot_id, changing=False)


@router.put(
    "/applicant/applications/{application_id}/exam-booking",
    response_model=ApplicationDetail,
)
def change_exam_session(
    application_id: int,
    body: ExamBookingRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> ApplicationDetail:
    """The applicant moves their own booking to another session with a
    free seat -- until 24 hours before the one they're in. After that
    only HR can move them."""
    application = own_application(db, application_id, user)
    instance = _exam_stage_instance(db, application, body.stage_type)
    if exam_scheduling.current_booking(db, instance) is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Your examination wasn't booked from a session, so contact the HR office to change it.",
        )
    return _book(db, user=user, application=application, instance=instance, exam_slot_id=body.exam_slot_id, changing=True)


@router.post(
    "/applicant/applications/{application_id}/exam-booking/none-work",
    response_model=ApplicationDetail,
)
def say_no_exam_session_works(
    application_id: int,
    body: ExamNoneWorkRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> ApplicationDetail:
    """None of the open sessions work for the applicant. Every HR admin is
    told and the profile shows it; the applicant is told when HR adds
    sessions."""
    application = own_application(db, application_id, user)
    instance = _exam_stage_instance(db, application, body.stage_type)
    if (instance.payload or {}).get("schedule"):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Your examination is already booked.")
    exam_scheduling.mark_none_work(instance, body.note)

    requisition = db.get(JobRequisition, application.requisition_id)
    stage_label = resolve_stage_label(body.stage_type.value, requisition)
    note = (body.note or "").strip()
    for hr_admin in db.scalars(select(User).where(User.role == UserRole.hr_admin)):
        notify(
            db,
            kind="schedule",
            user_id=hr_admin.id,
            actor_id=user.id,
            application_id=application.id,
            title="No exam session works",
            message=(
                f"{user.full_name} says none of the {stage_label} sessions for {requisition.title} work"
                + (f': "{note}"' if note else ".")
            ),
            link=f"/hr/applications/{application.id}?tab=examinations",
        )
    db.commit()
    return to_detail(db, application)


def _own_interview_instance(db: Session, application: CandidateApplication, stage_type: StageType) -> StageInstance:
    instance = db.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == stage_type,
        )
    )
    if instance is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="This application has no such interview stage."
        )
    return instance


@router.post(
    "/applicant/applications/{application_id}/interview-slot",
    response_model=ApplicationDetail,
)
def pick_interview_slot(
    application_id: int,
    body: InterviewSlotPickRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> ApplicationDetail:
    """The applicant picks one of the times HR sent. Picking is
    confirming: the time is booked and recorded as confirmed, and the
    evaluator is told. A time someone else just took is a 409."""
    application = own_application(db, application_id, user)
    if application.status != ApplicationStatus.active:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Only an active application can book an interview."
        )
    require_current_stage(application, body.stage_type)
    instance = _own_interview_instance(db, application, body.stage_type)
    requisition = db.get(JobRequisition, application.requisition_id)

    try:
        schedule = interview_scheduling.pick_slot(
            db, instance=instance, requisition=requisition, date=body.date, time=body.time
        )
    except interview_scheduling.SlotUnavailableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    stage_label = resolve_stage_label(body.stage_type.value, requisition)
    if instance.assigned_evaluator_id is not None:
        notify(
            db,
            kind="schedule",
            user_id=instance.assigned_evaluator_id,
            actor_id=user.id,
            application_id=application.id,
            title="Interview time picked",
            message=(
                f"{user.full_name} picked {schedule['date']} at {schedule['time']} "
                f"for their {stage_label} ({requisition.title})."
            ),
            link=f"/evaluator/interviews/{instance.id}",
        )
    db.commit()
    db.refresh(application)
    return to_detail(db, application)


@router.post(
    "/applicant/applications/{application_id}/interview-slot/decline",
    response_model=ApplicationDetail,
)
def decline_interview_slots(
    application_id: int,
    body: InterviewSlotDeclineRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> ApplicationDetail:
    """None of the sent times work. Tells HR, who send others -- like
    "I'm not available" on a time HR set, it does not touch the
    application itself."""
    application = own_application(db, application_id, user)
    if application.status != ApplicationStatus.active:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Only an active application can answer this."
        )
    require_current_stage(application, body.stage_type)
    instance = _own_interview_instance(db, application, body.stage_type)
    try:
        interview_scheduling.decline_offer(instance, note=body.note)
    except interview_scheduling.SlotUnavailableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    requisition = db.get(JobRequisition, application.requisition_id)
    stage_label = resolve_stage_label(body.stage_type.value, requisition)
    said = body.note.strip()
    detail = f': "{said}"' if said else "."
    for hr_admin in db.scalars(select(User).where(User.role == UserRole.hr_admin)):
        notify(
            db,
            kind="schedule",
            user_id=hr_admin.id,
            actor_id=user.id,
            application_id=application.id,
            title="No interview time works",
            message=f"None of the times sent work for {user.full_name}'s {stage_label}{detail}",
            link=f"/hr/applications/{application.id}",
        )
    db.commit()
    db.refresh(application)
    return to_detail(db, application)
