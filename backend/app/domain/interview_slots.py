"""Cutting an evaluator's free time into fixed interview slots.
Pure; dates are "YYYY-MM-DD" and times "HH:MM", as the browser sends them.
"""

from dataclasses import dataclass
from datetime import datetime

from app.domain.schedule_time import is_in_past

#: The lengths HR can pick for an interview round, in minutes.
ALLOWED_DURATIONS = (15, 30, 45, 60, 90)

# The lengths the workflow editor always showed as its defaults: the
# first two rounds 45 minutes, the later ones 30. Older jobs never saved
# one, so these stand in for them.
_LONG_ROUNDS = ("interview_round_1", "interview_round_2")


def default_duration(stage_type: str) -> int:
    if stage_type.startswith("interview_round_") and stage_type not in _LONG_ROUNDS:
        return 30
    return 45


def round_duration(stage_type: str, durations: dict[str, int] | None) -> int:
    """This round's slot length on a job: what HR saved, else the default."""
    saved = (durations or {}).get(stage_type)
    return saved if saved in ALLOWED_DURATIONS else default_duration(stage_type)


def to_minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass(frozen=True, order=True)
class Slot:
    date: str
    start: str
    end: str

    def overlaps(self, other: "Slot") -> bool:
        return (
            self.date == other.date
            and to_minutes(self.start) < to_minutes(other.end)
            and to_minutes(other.start) < to_minutes(self.end)
        )


def cut_into_slots(windows: list[Slot], minutes: int) -> list[Slot]:
    """Every whole slot of the round's length that fits in each window,
    back to back from its start (45 min: 9:00, 9:45, 10:30); a remainder
    too short for one more is left out. Sorted, with
    duplicates (overlapping windows) removed."""
    slots: set[Slot] = set()
    for window in windows:
        start, end = to_minutes(window.start), to_minutes(window.end)
        while start + minutes <= end:
            slots.add(Slot(window.date, to_hhmm(start), to_hhmm(start + minutes)))
            start += minutes
    return sorted(slots)


def is_taken(slot: Slot, busy: list[Slot]) -> bool:
    return any(slot.overlaps(other) for other in busy)


def open_slots(
    windows: list[Slot], minutes: int, busy: list[Slot], *, now: datetime | None = None
) -> list[Slot]:
    """The slots an applicant may still pick: cut from the evaluator's
    windows, not started yet, and clear of everything already booked
    with this evaluator on any job."""
    return [
        slot
        for slot in cut_into_slots(windows, minutes)
        if not is_in_past(slot.date, slot.start, now=now) and not is_taken(slot, busy)
    ]
