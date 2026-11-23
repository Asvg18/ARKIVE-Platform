"""The slot-cutting rules for interviews -- domain/interview_slots.py
(panel revision list, 15 Oct 2026, step 19b)."""

from datetime import datetime

from app.domain.interview_slots import (
    Slot,
    cut_into_slots,
    default_duration,
    open_slots,
    round_duration,
)
from app.domain.schedule_time import PHILIPPINE_TIME

# 15 Oct 2026, 2:00 PM in the Philippines
NOW = datetime(2026, 10, 15, 14, 0, tzinfo=PHILIPPINE_TIME)


def test_a_range_is_cut_into_back_to_back_slots():
    """The panel's own example: 45 minutes -> 9:00, 9:45, 10:30."""
    slots = cut_into_slots([Slot("2026-10-20", "09:00", "11:15")], 45)
    assert [(s.start, s.end) for s in slots] == [("09:00", "09:45"), ("09:45", "10:30"), ("10:30", "11:15")]


def test_a_remainder_too_short_for_a_slot_is_left_out():
    slots = cut_into_slots([Slot("2026-10-20", "09:00", "10:00")], 45)
    assert [(s.start, s.end) for s in slots] == [("09:00", "09:45")]
    assert cut_into_slots([Slot("2026-10-20", "09:00", "09:30")], 45) == []


def test_several_ranges_come_back_sorted_without_repeats():
    slots = cut_into_slots(
        [Slot("2026-10-21", "13:00", "14:00"), Slot("2026-10-20", "09:00", "10:00"), Slot("2026-10-20", "09:00", "10:00")],
        30,
    )
    assert [(s.date, s.start) for s in slots] == [
        ("2026-10-20", "09:00"),
        ("2026-10-20", "09:30"),
        ("2026-10-21", "13:00"),
        ("2026-10-21", "13:30"),
    ]


def test_a_slot_booked_with_the_same_evaluator_is_not_offered():
    """Overlap, not an exact match -- another job's 30-minute round at
    9:30 blocks the 9:00-9:45 and 9:45-10:30 slots of a 45-minute one."""
    busy = [Slot("2026-10-20", "09:30", "10:00")]
    slots = open_slots([Slot("2026-10-20", "09:00", "11:15")], 45, busy, now=NOW)
    assert [s.start for s in slots] == ["10:30"]


def test_slots_already_started_are_not_offered():
    slots = open_slots([Slot("2026-10-15", "13:00", "16:00")], 60, [], now=NOW)
    assert [s.start for s in slots] == ["14:00", "15:00"]


def test_round_lengths_fall_back_to_the_editor_defaults():
    assert default_duration("interview_round_1") == 45
    assert default_duration("interview_round_2") == 45
    assert default_duration("interview_round_3") == 30
    assert default_duration("interview_hr_director") == 45
    assert round_duration("interview_round_3", {"interview_round_3": 60}) == 60
    assert round_duration("interview_round_3", None) == 30
    # a stored value outside the allowed list is ignored, not trusted
    assert round_duration("interview_round_1", {"interview_round_1": 7}) == 45
