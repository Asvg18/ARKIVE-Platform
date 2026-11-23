"""Exam sessions: seat booking is capacity arithmetic, deliberately not
an LLM call.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.schedule_time import is_in_past, starts_within
from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus, ExamBookingStatus, StageStatus, StageType
from app.models.exam_slot import ExamSlot
from app.models.exam_slot_booking import ExamSlotBooking
from app.models.stage_instance import StageInstance
from app.models.user import User
from app.services.agents import EXAM_SCHEDULING

__all__ = [
    "CHANGE_CUTOFF_HOURS",
    "ExamChangeClosedError",
    "ExamSessionFullError",
    "ExamSessionUnchangedError",
    "SessionAttendee",
    "applicant_can_change",
    "book_session",
    "current_booking",
    "held_seats",
    "mark_none_work",
    "open_sessions",
    "reconcile_reopened",
    "release_bookings",
    "remaining_capacity",
    "session_schedule",
    "update_session",
    "waiting_applications",
]

# An applicant may change their own session until this long before it
# starts; after that only HR can move them.
CHANGE_CUTOFF_HOURS = 24

# A booking on an application that has left the running holds no seat:
# a rejected or withdrawn candidate's seat frees itself, whichever of the
# several ways the application was closed.
_CLOSED_APPLICATION_STATUSES = (ApplicationStatus.rejected, ApplicationStatus.withdrawn)


class ExamSessionFullError(Exception):
    """The session has no seat left, or has already started -- raised so
    the caller can turn it into a clean 409. A real, expected race (page
    loaded, the last seat went, then they pressed Book), not a bug."""


class ExamChangeClosedError(Exception):
    """The applicant's own session starts within the cut-off, so only HR
    can move them now."""


class ExamSessionUnchangedError(Exception):
    """A move to the session they're already booked in."""


@dataclass(frozen=True)
class SessionAttendee:
    """One person holding a seat in a session, for the HR roster."""

    application_id: int
    applicant: User


def _seat_holders(slot_id: int):
    """The bookings that hold a seat in this session: not denied, on an
    application still in the running."""
    return (
        select(ExamSlotBooking)
        .join(CandidateApplication, CandidateApplication.id == ExamSlotBooking.application_id)
        .where(
            ExamSlotBooking.exam_slot_id == slot_id,
            ExamSlotBooking.status != ExamBookingStatus.denied,
            CandidateApplication.status.notin_(_CLOSED_APPLICATION_STATUSES),
        )
    )


def remaining_capacity(db: Session, slot: ExamSlot) -> int:
    """Seats left: capacity minus every booking that holds a seat
    (including an older pending proposal). Below zero only after HR
    reopens a closed application (see reconcile_reopened)."""
    booked = db.scalar(select(func.count()).select_from(_seat_holders(slot.id).subquery()))
    return slot.capacity - booked


def held_seats(db: Session, slot_ids: list[int]) -> dict[int, list[SessionAttendee]]:
    """Who holds a seat in each of these sessions, in booking order -- the
    rosters, and their seat counts, for a whole list of sessions in one
    query."""
    rosters: dict[int, list[SessionAttendee]] = {slot_id: [] for slot_id in slot_ids}
    if not slot_ids:
        return rosters
    rows = db.execute(
        select(ExamSlotBooking.exam_slot_id, ExamSlotBooking.application_id, User)
        .join(CandidateApplication, CandidateApplication.id == ExamSlotBooking.application_id)
        .join(User, User.id == CandidateApplication.applicant_id)
        .where(
            ExamSlotBooking.exam_slot_id.in_(slot_ids),
            ExamSlotBooking.status != ExamBookingStatus.denied,
            CandidateApplication.status.notin_(_CLOSED_APPLICATION_STATUSES),
        )
        .order_by(ExamSlotBooking.id)
    ).all()
    for slot_id, application_id, user in rows:
        rosters[slot_id].append(SessionAttendee(application_id=application_id, applicant=user))
    return rosters


def open_sessions(
    db: Session, *, requisition_id: int, stage_type: str, exclude_slot_id: int | None = None
) -> list[tuple[ExamSlot, int]]:
    """The sessions an applicant may still pick for this job's exam
    stage, with seats left: not started yet and not full. Earliest
    first. `exclude_slot_id` leaves out the one they're already in."""
    slots = [
        slot
        for slot in db.scalars(
            select(ExamSlot)
            .where(ExamSlot.requisition_id == requisition_id, ExamSlot.stage_type == stage_type)
            .order_by(ExamSlot.date, ExamSlot.time)
        )
        if slot.id != exclude_slot_id and not is_in_past(slot.date, slot.time)
    ]
    # every session's seats from one roster query, not one count per session
    rosters = held_seats(db, [slot.id for slot in slots])
    sessions: list[tuple[ExamSlot, int]] = []
    for slot in slots:
        remaining = slot.capacity - len(rosters[slot.id])
        if remaining > 0:
            sessions.append((slot, remaining))
    return sessions


def session_schedule(slot: ExamSlot) -> dict:
    """The stage's `schedule` block for a booked session, plus the
    window's end when it has one."""
    schedule = {"date": slot.date, "time": slot.time, "location": slot.location}
    if slot.end_time:
        schedule["end_time"] = slot.end_time
    return schedule


def current_booking(db: Session, instance: StageInstance) -> ExamSlotBooking | None:
    """The session booking this exam stage holds now, if any. A pending
    proposal from the old flow is not a booking yet."""
    return db.scalar(
        select(ExamSlotBooking)
        .where(
            ExamSlotBooking.stage_instance_id == instance.id,
            ExamSlotBooking.status == ExamBookingStatus.approved,
        )
        .order_by(ExamSlotBooking.id.desc())
        .limit(1)
    )


def applicant_can_change(slot: ExamSlot, *, now: datetime | None = None) -> bool:
    """Whether the applicant may still change out of this session
    themselves: more than CHANGE_CUTOFF_HOURS before it starts."""
    return not starts_within(slot.date, slot.time, hours=CHANGE_CUTOFF_HOURS, now=now)


def book_session(
    db: Session,
    *,
    instance: StageInstance,
    exam_slot_id: int,
    enforce_cutoff: bool,
    booked_by: int | None = None,
) -> tuple[ExamSlotBooking, ExamSlot]:
    """Books a session for this exam stage, or moves the stage's booking
    to another one, and writes it onto the stage as its schedule: a
    booking is the only way an exam gets a time. Booked at once, no HR
    approval. Caller owns db.commit() and checks the session belongs to
    this job's stage.

    `enforce_cutoff` is the applicant's own change, refused within
    CHANGE_CUTOFF_HOURS of the session; HR moves people regardless.
    Every session involved is locked FOR UPDATE, in id order so two moves
    can't deadlock, and the seat count is recomputed under the lock, so
    two people can't both get the last seat."""
    current = current_booking(db, instance)
    if current is not None and current.exam_slot_id == exam_slot_id:
        raise ExamSessionUnchangedError("You're already booked in that session.")

    locked: dict[int, ExamSlot] = {}
    for slot_id in sorted({exam_slot_id, *([current.exam_slot_id] if current else [])}):
        row = db.scalar(select(ExamSlot).where(ExamSlot.id == slot_id).with_for_update())
        if row is not None:
            locked[slot_id] = row

    if current is not None and enforce_cutoff:
        held = locked.get(current.exam_slot_id)
        if held is not None and not applicant_can_change(held):
            raise ExamChangeClosedError(
                "Your session starts in less than 24 hours, so it can no longer be changed here. "
                "Contact the HR office to move it."
            )

    slot = locked.get(exam_slot_id)
    if slot is None or is_in_past(slot.date, slot.time):
        raise ExamSessionFullError("That session has already started. Please pick another.")
    remaining = remaining_capacity(db, slot)
    if remaining <= 0:
        raise ExamSessionFullError("That session has just filled up. Please pick another.")

    now = datetime.now(timezone.utc)
    # The seat this stage held, if any, and any proposal still pending
    # from the old Pre-Screening flow -- a real booking answers it.
    for held in db.scalars(
        select(ExamSlotBooking).where(
            ExamSlotBooking.stage_instance_id == instance.id,
            ExamSlotBooking.status != ExamBookingStatus.denied,
        )
    ):
        held.status = ExamBookingStatus.denied
        held.resolved_at = now
        held.resolved_by = booked_by
    booking = ExamSlotBooking(
        exam_slot_id=slot.id,
        application_id=instance.application_id,
        stage_instance_id=instance.id,
        applicant_selected_slot_ids=[slot.id],
        status=ExamBookingStatus.approved,
        resolved_at=now,
        resolved_by=booked_by,
    )
    db.add(booking)
    # Reassigned rather than mutated in place -- a plain JSON column has
    # no mutation tracking. A booking answers any "none of these work".
    payload = {**(instance.payload or {}), "schedule": session_schedule(slot)}
    payload.pop("exam_none_work", None)
    instance.payload = payload

    EXAM_SCHEDULING.log(
        db,
        application_id=instance.application_id,
        triggered_by_stage=instance.stage_type.value,
        output={
            "booked_slot_id": slot.id,
            "moved_from_slot_id": current.exam_slot_id if current else None,
            "remaining_capacity_before_booking": remaining,
            "reason": "booked_by_hr" if booked_by else "applicant_picked_a_session_with_a_free_seat",
        },
    )
    return booking, slot


def mark_none_work(instance: StageInstance, note: str | None) -> None:
    """Records that none of the open sessions work for the applicant, so
    HR's profile can say so. Cleared by their next booking."""
    instance.payload = {
        **(instance.payload or {}),
        "exam_none_work": {
            "note": (note or "").strip() or None,
            "at": datetime.now(timezone.utc).isoformat(),
        },
    }


def update_session(
    db: Session,
    slot: ExamSlot,
    *,
    date: str,
    time: str,
    end_time: str,
    location: str,
    capacity: int,
) -> list[StageInstance]:
    """HR's edit of one session. Refuses a session that has already
    started and seats below the number already booked. Every booked
    stage's schedule follows the new date, time and place; returns those
    stages when anything an attendee would care about changed (seats
    alone don't), so the caller can tell them. Caller owns db.commit()."""
    locked = db.scalar(select(ExamSlot).where(ExamSlot.id == slot.id).with_for_update())
    if is_in_past(locked.date, locked.time):
        raise ExamSessionFullError("This session has already started, so it can't be changed.")
    booked = locked.capacity - remaining_capacity(db, locked)
    if capacity < booked:
        raise ExamSessionFullError(
            f"{booked} {'person has' if booked == 1 else 'people have'} booked this session, "
            f"so it needs at least {booked} {'seat' if booked == 1 else 'seats'}."
        )

    moved = (locked.date, locked.time, locked.end_time, locked.location) != (date, time, end_time, location)
    locked.date, locked.time, locked.end_time, locked.location, locked.capacity = date, time, end_time, location, capacity
    if not moved:
        return []

    changed: list[StageInstance] = []
    for booking in db.scalars(_seat_holders(locked.id)):
        if booking.status != ExamBookingStatus.approved:
            continue
        instance = db.get(StageInstance, booking.stage_instance_id)
        if instance is None:
            continue
        instance.payload = {**(instance.payload or {}), "schedule": session_schedule(locked)}
        changed.append(instance)
    return changed


def waiting_applications(db: Session, *, requisition_id: int, stage_type: str) -> list[CandidateApplication]:
    """Active applications on this exam stage with no session yet -- the
    people to tell when new sessions open."""
    stage = StageType(stage_type)
    rows = db.execute(
        select(CandidateApplication, StageInstance)
        .join(StageInstance, StageInstance.application_id == CandidateApplication.id)
        .where(
            CandidateApplication.requisition_id == requisition_id,
            CandidateApplication.status == ApplicationStatus.active,
            CandidateApplication.current_stage == stage,
            StageInstance.stage_type == stage,
        )
    ).all()
    return [application for application, instance in rows if not (instance.payload or {}).get("schedule")]


def reconcile_reopened(db: Session, application: CandidateApplication) -> None:
    """After HR reopens a closed application its old future bookings hold
    seats again. One whose session filled up meanwhile is given back and
    its schedule cleared, so the session isn't oversold and the applicant
    simply picks again. Caller owns db.commit()."""
    db.flush()  # the reopened status has to count before seats are recounted
    now = datetime.now(timezone.utc)
    bookings = db.scalars(
        select(ExamSlotBooking).where(
            ExamSlotBooking.application_id == application.id,
            ExamSlotBooking.status == ExamBookingStatus.approved,
        )
    ).all()
    for booking in bookings:
        slot = db.get(ExamSlot, booking.exam_slot_id)
        if slot is None or is_in_past(slot.date, slot.time) or remaining_capacity(db, slot) >= 0:
            continue
        booking.status = ExamBookingStatus.denied
        booking.resolved_at = now
        instance = db.get(StageInstance, booking.stage_instance_id)
        if instance is not None and instance.status != StageStatus.complete:
            payload = dict(instance.payload or {})
            payload.pop("schedule", None)
            instance.payload = payload


def release_bookings(db: Session, *, stage_instance_id: int, resolved_by: int | None) -> None:
    """Gives back every seat this stage holds. Caller owns db.commit()."""
    held = db.scalars(
        select(ExamSlotBooking).where(
            ExamSlotBooking.stage_instance_id == stage_instance_id,
            ExamSlotBooking.status != ExamBookingStatus.denied,
        )
    ).all()
    now = datetime.now(timezone.utc)
    for booking in held:
        booking.status = ExamBookingStatus.denied
        booking.resolved_at = now
        booking.resolved_by = resolved_by
