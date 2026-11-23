"""Tests for refusing a schedule in the past -- domain/schedule_time.py
and the schedule forms that use it (panel revision list, 15 Oct 2026)."""

from datetime import datetime

import pytest

from app.domain.schedule_time import (
    PHILIPPINE_TIME,
    ensure_not_in_future,
    ensure_not_in_past,
    format_session,
    is_in_past,
    starts_within,
)
from app.schemas.evaluator import RescheduleRequestCreate
from app.schemas.pipeline import (
    ExamSessionUpdateRequest,
    ExamSlotCreateRequest,
    InterviewScheduleRequest,
    RescheduleResolveRequest,
)

# 15 Oct 2026, 2:00 PM in the Philippines
NOW = datetime(2026, 10, 15, 14, 0, tzinfo=PHILIPPINE_TIME)


def test_a_past_date_is_refused():
    with pytest.raises(ValueError, match="date has already passed"):
        ensure_not_in_past("2026-10-14", "16:00", now=NOW)


def test_an_earlier_time_today_is_refused():
    with pytest.raises(ValueError, match="time has already passed"):
        ensure_not_in_past("2026-10-15", "09:00", now=NOW)


def test_later_today_and_future_dates_are_allowed():
    ensure_not_in_past("2026-10-15", "16:00", now=NOW)
    ensure_not_in_past("2026-10-16", "08:00", now=NOW)


def test_an_unreadable_date_is_refused():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        ensure_not_in_past("next tuesday", "09:00", now=NOW)


def test_is_in_past_reads_a_session_start():
    assert is_in_past("2026-10-15", "09:00", now=NOW)
    assert not is_in_past("2026-10-15", "16:00", now=NOW)
    assert is_in_past("garbage", "09:00", now=NOW)


def test_starts_within_draws_the_24_hour_line_in_philippine_time():
    # NOW is 15 Oct 2026, 2:00 PM Philippine time
    assert not starts_within("2026-10-16", "15:00", hours=24, now=NOW)  # 25 hours away
    assert starts_within("2026-10-16", "13:00", hours=24, now=NOW)  # 23 hours away
    assert starts_within("2026-10-15", "10:00", hours=24, now=NOW)  # already started
    assert starts_within("someday", "09:00", hours=24, now=NOW)  # unreadable counts as too late
    # just after midnight in Manila is still the 16th there, whatever UTC says
    late = datetime(2026, 10, 15, 23, 30, tzinfo=PHILIPPINE_TIME)
    assert starts_within("2026-10-16", "00:30", hours=24, now=late)


def test_format_session_reads_like_the_screen():
    assert format_session("2030-03-01", "09:00", "11:30") == "Fri, 1 Mar 2030, 9:00 AM – 11:30 AM"
    assert format_session("2030-03-01", "13:05") == "Fri, 1 Mar 2030, 1:05 PM"
    assert format_session("2030-03-01", "00:15") == "Fri, 1 Mar 2030, 12:15 AM"


def test_a_date_taken_cannot_be_in_the_future():
    ensure_not_in_future("2026-10-15", now=NOW)
    ensure_not_in_future("2026-10-01", now=NOW)
    with pytest.raises(ValueError, match="hasn't happened yet"):
        ensure_not_in_future("2026-10-16", now=NOW)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        ensure_not_in_future("soon", now=NOW)


@pytest.mark.parametrize(
    "build",
    [
        lambda: ExamSessionUpdateRequest(date="2020-01-01", start="09:00", end="11:00", location="Room 1", seats=5),
        lambda: InterviewScheduleRequest(stage_type="interview_round_1", date="2020-01-01", time="09:00", location="Room 1"),
        lambda: ExamSlotCreateRequest(stage_type="examination", date="2020-01-01", time="09:00", location="Room 1", capacity=5),
        lambda: RescheduleResolveRequest(decision="approve", date="2020-01-01", time="09:00"),
        lambda: RescheduleRequestCreate(proposed_date="2020-01-01", proposed_time="09:00"),
    ],
)
def test_every_schedule_form_refuses_a_past_date(build):
    with pytest.raises(ValueError, match="date has already passed"):
        build()


def test_denying_a_reschedule_needs_no_date():
    RescheduleResolveRequest(decision="deny")


def test_the_api_refuses_a_past_exam_session(client, make_job, hr_admin):
    from tests.conftest import auth_headers

    job = make_job(["document_upload", "examination", "final_decision"])
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        f"/hr/requisitions/{job.id}/exam-slots/batch",
        json={"stage_type": "examination", "dates": ["2020-01-01"], "windows": [{"start": "09:00", "end": "11:00"}],
              "seats": 5, "location": "Room 1"},
        headers=headers,
    )

    assert resp.status_code == 422
    assert "date has already passed" in resp.text
