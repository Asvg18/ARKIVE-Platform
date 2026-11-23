"""The confirmation an applicant gives against a scheduled stage.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.stage_instance import StageInstance

__all__ = [
    "CONFIRMED",
    "UNAVAILABLE",
    "ScheduleConfirmationUnavailableError",
    "open_confirmation",
    "read_confirmation",
    "respond",
    "time_confirmed",
]

CONFIRMED = "confirmed"
UNAVAILABLE = "unavailable"

_KEY = "schedule_confirmation"
_SCHEDULE_KEY = "schedule"


class ScheduleConfirmationUnavailableError(Exception):
    """There is nothing for this applicant to answer -- the stage isn't
    scheduled, or they have already answered this scheduling of it.
    Routers turn it into a 409."""


def read_confirmation(instance: StageInstance | None) -> dict | None:
    """The confirmation block on the stage's payload, beside the
    `schedule` it answers; None when nothing is being asked (unscheduled,
    or scheduled before confirmations existed)."""
    if instance is None:
        return None
    confirmation = (instance.payload or {}).get(_KEY)
    return confirmation if isinstance(confirmation, dict) else None


def time_confirmed(instance: StageInstance | None) -> bool:
    """Whether the applicant has confirmed the booked time -- what the
    evaluator's scorecard waits on, so nobody scores an interview
    nobody had agreed to.

    No time booked: not confirmed. No confirmation block (booked before
    confirmations existed): confirmed. Otherwise only an explicit yes (a
    picked slot records one); an open question or "I'm not available"
    keeps it waiting.
    """
    payload = (instance.payload or {}) if instance else {}
    if not isinstance(payload.get(_SCHEDULE_KEY), dict):
        return False
    confirmation = payload.get(_KEY)
    if not isinstance(confirmation, dict):
        return True
    return confirmation.get("response") == CONFIRMED


def open_confirmation(instance: StageInstance) -> dict:
    """Asks the applicant to confirm this scheduling. Caller owns
    db.commit().

    Deliberately *not* idempotent: every call (HR setting or changing the
    time) replaces any previous answer, since a yes to the old time says
    nothing about the new one.
    """
    payload = instance.payload or {}
    confirmation = {
        "response": None,
        "asked_at": datetime.now(timezone.utc).isoformat(),
        "responded_at": None,
        "note": None,
    }
    # Reassigned rather than mutated in place -- a plain JSON column has
    # no mutation tracking, so setting a key on the nested dict would
    # never be flushed.
    instance.payload = {**payload, _KEY: confirmation}
    return confirmation


def respond(
    db: Session, *, instance: StageInstance, response: str, note: str | None = None
) -> dict:
    """Records the applicant's answer. `unavailable` records a clash, not a
    withdrawal: application status is untouched. Caller owns db.commit()
    and telling HR about an `unavailable`.
    """
    payload = instance.payload or {}
    if not isinstance(payload.get(_SCHEDULE_KEY), dict):
        raise ScheduleConfirmationUnavailableError(
            "This stage has not been scheduled yet, so there is nothing to confirm."
        )

    confirmation = payload.get(_KEY)
    if not isinstance(confirmation, dict):
        raise ScheduleConfirmationUnavailableError(
            "There is nothing to confirm on this stage."
        )
    if confirmation.get("response"):
        raise ScheduleConfirmationUnavailableError(
            "You have already answered this. If something has changed, contact the HR office."
        )

    answered = {
        **confirmation,
        "response": response,
        "responded_at": datetime.now(timezone.utc).isoformat(),
        "note": (note or "").strip() or None,
    }
    instance.payload = {**payload, _KEY: answered}
    return answered
