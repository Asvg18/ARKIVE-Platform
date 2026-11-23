"""Interview scheduling, evaluator → HR → applicant: availability_windows,
send_offer, then pick_slot. Callers own db.commit() and notifying.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.interview_slots import Slot, cut_into_slots, is_taken, open_slots, round_duration, to_hhmm, to_minutes
from app.domain.schedule_time import is_in_past
from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus
from app.models.interview_availability import InterviewAvailability
from app.models.job_requisition import JobRequisition
from app.models.stage_instance import StageInstance
from app.models.user import User
from app.services import schedule_confirmation

__all__ = [
    "NONE_WORK",
    "PICKED",
    "SlotUnavailableError",
    "availability_windows",
    "busy_slots",
    "decline_offer",
    "open_offer_slots",
    "pick_slot",
    "read_offer",
    "send_offer",
    "slot_choices",
]

PICKED = "picked"
NONE_WORK = "none_work"

_OFFER_KEY = "slot_offer"


class SlotUnavailableError(Exception):
    """The time asked for isn't on offer any more -- taken by someone
    else, already started, or never sent. Routers turn it into a 409."""


def read_offer(instance: StageInstance | None) -> dict | None:
    offer = ((instance.payload or {}) if instance else {}).get(_OFFER_KEY)
    return offer if isinstance(offer, dict) else None


def availability_windows(db: Session, instance: StageInstance) -> list[InterviewAvailability]:
    """Step 1: the ranges the assigned evaluator is free in for this round
    (InterviewAvailability rows), in order. A previous evaluator's ranges
    are left out, not deleted."""
    if instance.assigned_evaluator_id is None:
        return []
    return list(
        db.scalars(
            select(InterviewAvailability)
            .where(
                InterviewAvailability.stage_instance_id == instance.id,
                InterviewAvailability.evaluator_id == instance.assigned_evaluator_id,
            )
            .order_by(InterviewAvailability.date, InterviewAvailability.start_time)
        )
    )


def _windows(rows: list[InterviewAvailability]) -> list[Slot]:
    return [Slot(row.date, row.start_time, row.end_time) for row in rows]


def busy_slots(db: Session, evaluator_id: int, *, exclude_instance_id: int) -> list[Slot]:
    """Every interview already booked with this evaluator, on any job,
    except the round being scheduled, read from the booked schedules
    themselves; this is what makes a slot one applicant took disappear for
    every other candidate. A time without an end (set by hand) lasts its
    round's length. Only candidates still in the running count."""
    rows = db.execute(
        select(StageInstance, JobRequisition.interview_durations)
        .join(CandidateApplication, CandidateApplication.id == StageInstance.application_id)
        .join(JobRequisition, JobRequisition.id == CandidateApplication.requisition_id)
        .where(
            StageInstance.assigned_evaluator_id == evaluator_id,
            StageInstance.id != exclude_instance_id,
            CandidateApplication.status == ApplicationStatus.active,
        )
    ).all()
    busy: list[Slot] = []
    for instance, durations in rows:
        schedule = (instance.payload or {}).get("schedule")
        if not isinstance(schedule, dict) or not schedule.get("date") or not schedule.get("time"):
            continue
        try:
            start = to_minutes(schedule["time"])
            end = (
                to_minutes(schedule["end_time"])
                if schedule.get("end_time")
                else start + round_duration(instance.stage_type.value, durations)
            )
        except (ValueError, AttributeError):
            continue
        busy.append(Slot(schedule["date"], to_hhmm(start), to_hhmm(min(end, 24 * 60 - 1))))
    return busy


def slot_choices(
    db: Session, instance: StageInstance, requisition: JobRequisition
) -> list[tuple[Slot, bool]]:
    """What HR picks from: the evaluator's ranges cut into slots, still
    to come, each marked taken when it clashes with another interview of
    the same evaluator."""
    if instance.assigned_evaluator_id is None:
        return []
    minutes = round_duration(instance.stage_type.value, requisition.interview_durations)
    busy = busy_slots(db, instance.assigned_evaluator_id, exclude_instance_id=instance.id)
    return [
        (slot, is_taken(slot, busy))
        for slot in cut_into_slots(_windows(availability_windows(db, instance)), minutes)
        if not is_in_past(slot.date, slot.start)
    ]


def open_offer_slots(db: Session, instance: StageInstance, requisition: JobRequisition) -> list[Slot]:
    """The sent slots the applicant can still pick: sent by HR, still in
    the evaluator's ranges, not started, not taken since."""
    offer = read_offer(instance)
    if offer is None or instance.assigned_evaluator_id is None:
        return []
    minutes = round_duration(instance.stage_type.value, requisition.interview_durations)
    busy = busy_slots(db, instance.assigned_evaluator_id, exclude_instance_id=instance.id)
    still_open = {
        (slot.date, slot.start): slot
        for slot in open_slots(_windows(availability_windows(db, instance)), minutes, busy)
    }
    sent = [(s.get("date"), s.get("time")) for s in offer.get("slots") or [] if isinstance(s, dict)]
    return sorted(still_open[key] for key in set(sent) if key in still_open)


def send_offer(
    db: Session,
    *,
    instance: StageInstance,
    requisition: JobRequisition,
    slots: list[tuple[str, str]],
    mode: str,
    location: str | None,
    meeting_link: str | None,
) -> dict:
    """Step 2: sends HR's chosen slots (the evaluator's ranges cut by the
    round's length), with where, stored as `slot_offer` on the round's
    payload. Every slot must still be free; sending replaces any earlier
    offer and any schedule on the round, so the applicant picks afresh."""
    if instance.assigned_evaluator_id is None:
        raise SlotUnavailableError("Assign an evaluator to this round first.")
    choices = {(slot.date, slot.start): (slot, taken) for slot, taken in slot_choices(db, instance, requisition)}
    for key in slots:
        choice = choices.get(key)
        if choice is None or choice[1]:
            raise SlotUnavailableError(
                "Some of these times are no longer free. Refresh the page and pick again."
            )
    offer = {
        "slots": [{"date": date, "time": time} for date, time in sorted(set(slots))],
        "duration_minutes": round_duration(instance.stage_type.value, requisition.interview_durations),
        "mode": mode,
        "location": location if mode == "in_person" else None,
        "meeting_link": meeting_link if mode == "online" else None,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "response": None,
        "note": None,
        "responded_at": None,
    }
    payload = {
        key: value
        for key, value in (instance.payload or {}).items()
        if key not in ("schedule", "schedule_confirmation")
    }
    # Reassigned rather than mutated in place -- a plain JSON column has
    # no mutation tracking.
    instance.payload = {**payload, _OFFER_KEY: offer}
    return offer


def pick_slot(
    db: Session, *, instance: StageInstance, requisition: JobRequisition, date: str, time: str
) -> dict:
    """Step 3, the applicant's pick: picking is confirming, so it writes
    the round's `schedule` and records it as confirmed
    (services/schedule_confirmation). Returns the schedule.

    The evaluator's user row is locked first, so two candidates racing
    for the same evaluator's last slot are served one at a time and the
    second is refused rather than double-booked."""
    offer = read_offer(instance)
    if offer is None or offer.get("response") == PICKED or (instance.payload or {}).get("schedule"):
        raise SlotUnavailableError("There is no time to pick on this interview.")
    if instance.assigned_evaluator_id is not None:
        db.scalar(select(User).where(User.id == instance.assigned_evaluator_id).with_for_update())
    chosen = next((s for s in open_offer_slots(db, instance, requisition) if (s.date, s.start) == (date, time)), None)
    if chosen is None:
        raise SlotUnavailableError("That time was just taken. Please pick another.")

    schedule = {
        "date": chosen.date,
        "time": chosen.start,
        "end_time": chosen.end,
        "mode": offer.get("mode") or "in_person",
        "location": offer.get("location"),
        "meeting_link": offer.get("meeting_link"),
    }
    now = datetime.now(timezone.utc).isoformat()
    instance.payload = {
        **(instance.payload or {}),
        "schedule": schedule,
        _OFFER_KEY: {**offer, "response": PICKED, "responded_at": now},
    }
    # Picking is confirming: asked and answered in one go,
    # through the same module HR's own scheduling uses.
    schedule_confirmation.open_confirmation(instance)
    schedule_confirmation.respond(db, instance=instance, response=schedule_confirmation.CONFIRMED)
    return schedule


def decline_offer(instance: StageInstance, *, note: str | None) -> dict:
    """None of the sent times work. Recorded on the offer for HR, who
    send others; the application itself is untouched."""
    offer = read_offer(instance)
    if offer is None or offer.get("response") or (instance.payload or {}).get("schedule"):
        raise SlotUnavailableError("There is nothing to answer on this interview.")
    answered = {
        **offer,
        "response": NONE_WORK,
        "note": (note or "").strip() or None,
        "responded_at": datetime.now(timezone.utc).isoformat(),
    }
    instance.payload = {**(instance.payload or {}), _OFFER_KEY: answered}
    return answered
