"""A job's face-to-face examination sessions, their rosters, and HR
booking applicants into them.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.hr.common import PIPELINE_ROLES
from app.domain.schedule_time import format_session
from app.infra.db import get_db
from app.infra.deps import require_role
from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus, ExamBookingStatus, StageStatus
from app.models.exam_slot import ExamSlot
from app.models.exam_slot_booking import ExamSlotBooking
from app.models.job_requisition import JobRequisition
from app.models.stage_instance import StageInstance
from app.models.user import User
from app.schemas.pipeline import (
    CandidateProfile,
    ExamBookingResolveRequest,
    ExamSessionAttendee,
    ExamSessionBatchRequest,
    ExamSessionBatchResult,
    ExamSessionUpdateRequest,
    ExamSlotCreateRequest,
    ExamSlotRead,
    HrExamBookingRequest,
)
from app.schemas.user import avatar_url
from app.services import exam_scheduling
from app.services.candidate_profile import build_candidate_profile
from app.services.email import send_email_safely
from app.services.notifications import notify
from app.services.stage_labels import resolve_stage_label

router = APIRouter(tags=["exam-slots"])


def _exam_slot_reads(db: Session, slots: list[ExamSlot]) -> list[ExamSlotRead]:
    """The sessions with their seats left and rosters, from one roster
    query for the whole list."""
    rosters = exam_scheduling.held_seats(db, [slot.id for slot in slots])
    return [
        ExamSlotRead(
            id=slot.id,
            stage_type=slot.stage_type,
            date=slot.date,
            time=slot.time,
            end_time=slot.end_time,
            location=slot.location,
            capacity=slot.capacity,
            remaining_capacity=slot.capacity - len(rosters[slot.id]),
            booked=[
                ExamSessionAttendee(
                    application_id=seat.application_id,
                    applicant_name=seat.applicant.full_name,
                    avatar_url=avatar_url(seat.applicant.avatar_file),
                )
                for seat in rosters[slot.id]
            ],
        )
        for slot in slots
    ]


def _job_with_exam_stage(db: Session, requisition_id: int, stage_type: str) -> JobRequisition:
    requisition = db.get(JobRequisition, requisition_id)
    if requisition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Requisition not found")
    if stage_type not in requisition.workflow_definition:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="This job's workflow doesn't include that examination stage.",
        )
    return requisition


def _tell_applicant(
    db: Session,
    *,
    application: CandidateApplication,
    requisition: JobRequisition,
    actor: User,
    subject: str,
    message: str,
    email_lines: list[str],
) -> None:
    """Tells the applicant about an exam-session change, in the app and by
    email. `actor` is the HR admin; a mail failure never undoes the
    change."""
    notify(
        db,
        kind="schedule",
        user_id=application.applicant_id,
        actor_id=actor.id,
        application_id=application.id,
        title=subject,
        message=message,
        link=f"/applicant/applications/{application.id}",
    )
    applicant = db.get(User, application.applicant_id)
    if applicant is not None:
        send_email_safely(
            to=applicant.email,
            subject=f"{subject}: {requisition.title}",
            body=f"Hi {applicant.full_name},\n\n" + "\n".join(email_lines) + "\n",
        )


def _tell_waiting_applicants(db: Session, requisition: JobRequisition, stage_type: str, actor: User) -> None:
    """New sessions are open: tells everyone waiting on this exam with no
    session yet, so a "none of these work" gets its answer."""
    stage_label = resolve_stage_label(stage_type, requisition)
    for application in exam_scheduling.waiting_applications(
        db, requisition_id=requisition.id, stage_type=stage_type
    ):
        _tell_applicant(
            db,
            application=application,
            requisition=requisition,
            actor=actor,
            subject=f"New {stage_label} sessions are open",
            message=f"New sessions are open for your {stage_label}. Pick one on your application page.",
            email_lines=[
                f"New sessions are open for your {stage_label} for {requisition.title}.",
                "",
                "Pick the one that suits you on your application page.",
            ],
        )


@router.get("/hr/requisitions/{requisition_id}/exam-slots", response_model=list[ExamSlotRead])
def list_exam_slots(
    requisition_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> list[ExamSlotRead]:
    if db.get(JobRequisition, requisition_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Requisition not found")
    rows = db.scalars(
        select(ExamSlot)
        .where(ExamSlot.requisition_id == requisition_id)
        .order_by(ExamSlot.date, ExamSlot.time)
    ).all()
    return _exam_slot_reads(db, list(rows))


@router.post(
    "/hr/requisitions/{requisition_id}/exam-slots",
    response_model=ExamSlotRead,
    status_code=status.HTTP_201_CREATED,
)
def add_exam_slot(
    requisition_id: int,
    body: ExamSlotCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> ExamSlotRead:
    """Slot creation is always unlocked -- adding capacity is pure
    upside and never invalidates anything already scheduled."""
    requisition = _job_with_exam_stage(db, requisition_id, body.stage_type.value)
    row = ExamSlot(
        requisition_id=requisition_id,
        stage_type=body.stage_type.value,
        date=body.date,
        time=body.time,
        location=body.location,
        capacity=body.capacity,
    )
    db.add(row)
    db.flush()
    _tell_waiting_applicants(db, requisition, body.stage_type.value, user)
    db.commit()
    db.refresh(row)
    return _exam_slot_reads(db, [row])[0]


@router.post(
    "/hr/requisitions/{requisition_id}/exam-slots/batch",
    response_model=ExamSessionBatchResult,
    status_code=status.HTTP_201_CREATED,
)
def add_exam_sessions(
    requisition_id: int,
    body: ExamSessionBatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> ExamSessionBatchResult:
    """HR's "Add sessions": every picked date crossed with every time
    window, all with the same seats and place, created in one go. A
    session the job already has (same exam, date, time and place) is
    left out and counted, rather than refusing the whole batch."""
    requisition = _job_with_exam_stage(db, requisition_id, body.stage_type.value)
    existing = {
        (slot.date, slot.time, slot.end_time, slot.location.casefold())
        for slot in db.scalars(
            select(ExamSlot).where(
                ExamSlot.requisition_id == requisition_id,
                ExamSlot.stage_type == body.stage_type.value,
            )
        )
    }
    rows: list[ExamSlot] = []
    skipped = 0
    for day in sorted(body.dates):
        for window in sorted(body.windows, key=lambda w: w.start):
            if (day, window.start, window.end, body.location.casefold()) in existing:
                skipped += 1
                continue
            rows.append(
                ExamSlot(
                    requisition_id=requisition_id,
                    stage_type=body.stage_type.value,
                    date=day,
                    time=window.start,
                    end_time=window.end,
                    location=body.location,
                    capacity=body.seats,
                )
            )
    db.add_all(rows)
    db.flush()
    if rows:
        _tell_waiting_applicants(db, requisition, body.stage_type.value, user)
    db.commit()
    for row in rows:
        db.refresh(row)
    return ExamSessionBatchResult(created=_exam_slot_reads(db, rows), skipped=skipped)


@router.patch("/hr/requisitions/{requisition_id}/exam-slots/{slot_id}", response_model=ExamSlotRead)
def edit_exam_slot(
    requisition_id: int,
    slot_id: int,
    body: ExamSessionUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> ExamSlotRead:
    """Moves a session, changes its room or its seats. Everyone booked
    in it is told when its date, time
    or place changes; seats can't drop below the number already booked."""
    slot = db.scalar(select(ExamSlot).where(ExamSlot.id == slot_id, ExamSlot.requisition_id == requisition_id))
    if slot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Exam session not found.")
    clash = db.scalar(
        select(ExamSlot).where(
            ExamSlot.requisition_id == requisition_id,
            ExamSlot.stage_type == slot.stage_type,
            ExamSlot.id != slot.id,
            ExamSlot.date == body.date,
            ExamSlot.time == body.start,
            ExamSlot.end_time == body.end,
            func.lower(ExamSlot.location) == body.location.lower(),
        )
    )
    if clash is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="The job already has a session at that time and place.")

    try:
        moved = exam_scheduling.update_session(
            db, slot, date=body.date, time=body.start, end_time=body.end, location=body.location, capacity=body.seats
        )
    except exam_scheduling.ExamSessionFullError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    requisition = db.get(JobRequisition, requisition_id)
    stage_label = resolve_stage_label(slot.stage_type, requisition)
    when = format_session(slot.date, slot.time, slot.end_time)
    for instance in moved:
        application = db.get(CandidateApplication, instance.application_id)
        if application is None:
            continue
        _tell_applicant(
            db,
            application=application,
            requisition=requisition,
            actor=user,
            subject=f"Your {stage_label} session has changed",
            message=f"Your {stage_label} session has changed. It is now {when}, at {slot.location}.",
            email_lines=[
                f"Your {stage_label} session for {requisition.title} has changed. It is now:",
                "",
                f"  When: {when}",
                f"  Where: {slot.location}",
                "",
                "You can review this any time on your application page.",
            ],
        )
    db.commit()
    db.refresh(slot)
    return _exam_slot_reads(db, [slot])[0]


@router.delete(
    "/hr/requisitions/{requisition_id}/exam-slots/{slot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_exam_slot(
    requisition_id: int,
    slot_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> None:
    row = db.scalar(
        select(ExamSlot).where(ExamSlot.id == slot_id, ExamSlot.requisition_id == requisition_id)
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Exam slot not found.")

    # refused while anyone holds a seat (move them first)
    if exam_scheduling.remaining_capacity(db, row) < row.capacity:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Someone has booked this session, so it can't be deleted. Move them to another session first.",
        )

    # spent bookings hold no seat but still reference the session, so
    # they are deleted with it
    for spent in db.scalars(select(ExamSlotBooking).where(ExamSlotBooking.exam_slot_id == slot_id)):
        db.delete(spent)
    db.flush()
    db.delete(row)
    db.commit()


@router.post("/hr/applications/{application_id}/exam-booking", response_model=CandidateProfile)
def book_exam_session_for_applicant(
    application_id: int,
    body: HrExamBookingRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> CandidateProfile:
    """HR books an applicant into one of the job's sessions, or moves them to
    another. There is no one-off exam time: every exam is a seat in a real
    session. HR isn't held to the applicant's 24-hour cut-off, only to the
    seat limit."""
    application = db.get(CandidateApplication, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found")
    if application.status != ApplicationStatus.active:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Only an active application can be booked into an exam.")
    requisition = _job_with_exam_stage(db, application.requisition_id, body.stage_type.value)

    instance = db.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == body.stage_type,
        )
    )
    if instance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This application has no such examination stage.")
    if instance.status in (StageStatus.complete, StageStatus.skipped):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This exam is already over for this applicant.")

    slot = db.get(ExamSlot, body.exam_slot_id)
    if slot is None or slot.requisition_id != requisition.id or slot.stage_type != body.stage_type.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Exam session not found.")

    moving = exam_scheduling.current_booking(db, instance) is not None or bool((instance.payload or {}).get("schedule"))
    try:
        exam_scheduling.book_session(
            db, instance=instance, exam_slot_id=slot.id, enforce_cutoff=False, booked_by=user.id
        )
    except exam_scheduling.ExamSessionUnchangedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="They're already booked in that session.") from exc
    except exam_scheduling.ExamSessionFullError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    stage_label = resolve_stage_label(body.stage_type.value, requisition)
    when = format_session(slot.date, slot.time, slot.end_time)
    _tell_applicant(
        db,
        application=application,
        requisition=requisition,
        actor=user,
        subject=f"Your {stage_label} is {'moved' if moving else 'booked'}",
        message=(
            f"HR {'moved' if moving else 'booked'} your {stage_label} "
            f"{'to' if moving else 'for'} {when}, at {slot.location}."
        ),
        email_lines=[
            f"HR has {'moved' if moving else 'booked'} your {stage_label} for {requisition.title}:",
            "",
            f"  When: {when}",
            f"  Where: {slot.location}",
            "",
            "You can review this any time on your application page.",
        ],
    )
    db.commit()
    return build_candidate_profile(db, application_id)


@router.post(
    "/hr/applications/{application_id}/exam-bookings/{booking_id}/resolve",
    response_model=CandidateProfile,
)
def resolve_exam_booking(
    application_id: int,
    booking_id: int,
    body: ExamBookingResolveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> CandidateProfile:
    """HR approves or denies an older pending exam-slot proposal. Approve
    re-checks capacity against approved bookings and writes the schedule
    onto the stage; deny leaves the candidate to pick (or be booked into)
    a session."""
    booking = db.get(ExamSlotBooking, booking_id)
    if booking is None or booking.application_id != application_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Exam booking not found")
    if booking.status != ExamBookingStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This booking has already been resolved.")

    instance = db.get(StageInstance, booking.stage_instance_id)
    if instance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Exam booking not found")

    if body.decision == "approve":
        target_slot_id = body.exam_slot_id or booking.exam_slot_id
        slot = db.get(ExamSlot, target_slot_id)
        if slot is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Exam slot not found.")
        approved_count = db.scalar(
            select(func.count())
            .select_from(ExamSlotBooking)
            .where(
                ExamSlotBooking.exam_slot_id == target_slot_id,
                ExamSlotBooking.status == ExamBookingStatus.approved,
            )
        )
        if slot.capacity - approved_count <= 0:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="That slot is already fully booked. Choose a different one.",
            )
        instance.payload = {
            **(instance.payload or {}),
            "schedule": exam_scheduling.session_schedule(slot),
        }
        booking.exam_slot_id = target_slot_id
        booking.status = ExamBookingStatus.approved
    else:
        booking.status = ExamBookingStatus.denied

    booking.resolved_at = datetime.now(timezone.utc)
    booking.resolved_by = user.id
    db.commit()
    return build_candidate_profile(db, application_id)
