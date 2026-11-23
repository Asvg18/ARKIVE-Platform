"""The exam-session rules added in revisions 2.0 (16 Oct 2026): the
applicant changes their own session until 24 hours before it; HR books or
moves anyone, held only to the seat limit; HR edits a session and its
bookers are told; "none of these work" reaches HR and new sessions reach
the applicant; seats free themselves when an application closes; and the
roster shows who booked each session."""

from datetime import timedelta

from sqlalchemy import select

from app.domain.schedule_time import now_in_philippines
from app.models.enums import ExamBookingStatus, StageType, UserRole
from app.models.exam_slot_booking import ExamSlotBooking
from app.models.notification import Notification
from app.services.applications import create_application_with_stage_instances
from tests.conftest import auth_headers
from tests.test_exam_sessions import EXAM_WORKFLOW, _exam_instance, _on_exam_stage, _session

BOOK = "/applicant/applications/{}/exam-booking"


def _soon(hours: float) -> tuple[str, str]:
    """A (date, time) `hours` from now, Philippine time."""
    at = now_in_philippines() + timedelta(hours=hours)
    return at.strftime("%Y-%m-%d"), at.strftime("%H:%M")


def _book(client, headers, application, slot, method="post"):
    return getattr(client, method)(
        BOOK.format(application.id),
        headers=headers,
        json={"stage_type": "examination", "exam_slot_id": slot.id},
    )


def _notices(db_session, user):
    return db_session.scalars(select(Notification).where(Notification.user_id == user.id)).all()


def _second_applicant(db_session, make_user, job, email="second-applicant@arkivetesting.com"):
    user = make_user(email, UserRole.applicant)
    application = create_application_with_stage_instances(db_session, applicant_id=user.id, requisition=job)
    db_session.flush()
    return user, application


# --- the applicant changes their own session -------------------------------


def test_an_applicant_can_change_session_until_24_hours_before(
    client, db_session, applicant, make_job, make_application
):
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    instance = _on_exam_stage(db_session, application)
    first = _session(db_session, job, capacity=3)
    second = _session(db_session, job, date="2030-03-02", capacity=3)
    headers = auth_headers(client, applicant.email)
    _book(client, headers, application, first)

    detail = client.get(f"/applicant/applications/{application.id}", headers=headers).json()
    assert detail["exam_booking"]["slot_id"] == first.id
    assert detail["exam_booking"]["can_change"] is True
    # the others they could change to, without the one they're in
    assert [s["id"] for s in detail["exam_sessions"]] == [second.id]

    resp = _book(client, headers, application, second, method="put")
    assert resp.status_code == 200, resp.text
    assert resp.json()["exam_booking"]["slot_id"] == second.id
    held = db_session.scalars(
        select(ExamSlotBooking).where(ExamSlotBooking.stage_instance_id == instance.id).order_by(ExamSlotBooking.id)
    ).all()
    assert [(b.exam_slot_id, b.status) for b in held] == [
        (first.id, ExamBookingStatus.denied),
        (second.id, ExamBookingStatus.approved),
    ]


def test_changing_is_closed_inside_24_hours(client, db_session, applicant, make_job, make_application):
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    _on_exam_stage(db_session, application)
    day, time = _soon(hours=5)
    soon = _session(db_session, job, date=day, time=time, end_time=None)
    later = _session(db_session, job, date="2030-03-02")
    headers = auth_headers(client, applicant.email)
    assert _book(client, headers, application, soon).status_code == 200

    detail = client.get(f"/applicant/applications/{application.id}", headers=headers).json()
    assert detail["exam_booking"]["can_change"] is False
    assert detail["exam_sessions"] == []

    resp = _book(client, headers, application, later, method="put")
    assert resp.status_code == 409
    assert "less than 24 hours" in resp.json()["detail"]


def test_changing_to_the_same_session_or_without_a_booking_is_refused(
    client, db_session, applicant, make_job, make_application
):
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    _on_exam_stage(db_session, application)
    slot = _session(db_session, job)
    headers = auth_headers(client, applicant.email)

    resp = _book(client, headers, application, slot, method="put")
    assert resp.status_code == 409  # nothing booked yet

    _book(client, headers, application, slot)
    resp = _book(client, headers, application, slot, method="put")
    assert resp.status_code == 409
    assert "already booked in that session" in resp.json()["detail"]


def test_the_last_seat_goes_to_one_applicant_only(
    client, db_session, applicant, make_user, make_job, make_application
):
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    _on_exam_stage(db_session, application)
    other_user, other_application = _second_applicant(db_session, make_user, job)
    _on_exam_stage(db_session, other_application)
    last_seat = _session(db_session, job, capacity=1)

    assert _book(client, auth_headers(client, applicant.email), application, last_seat).status_code == 200
    resp = _book(client, auth_headers(client, other_user.email), other_application, last_seat)
    assert resp.status_code == 409
    assert "filled up" in resp.json()["detail"]


# --- HR books and moves -----------------------------------------------------


def test_hr_ignores_the_cutoff_but_not_the_seat_limit(
    client, db_session, applicant, hr_admin, make_job, make_application
):
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    _on_exam_stage(db_session, application)
    day, time = _soon(hours=3)
    soon = _session(db_session, job, date=day, time=time, end_time=None)
    full = _session(db_session, job, date="2030-03-05", capacity=0)
    later = _session(db_session, job, date="2030-03-06")
    _book(client, auth_headers(client, applicant.email), application, soon)
    hr = auth_headers(client, hr_admin.email)
    url = f"/hr/applications/{application.id}/exam-booking"

    resp = client.post(url, headers=hr, json={"stage_type": "examination", "exam_slot_id": full.id})
    assert resp.status_code == 409
    assert "filled up" in resp.json()["detail"]

    resp = client.post(url, headers=hr, json={"stage_type": "examination", "exam_slot_id": later.id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["examinations"]["examination"]["booked_slot_id"] == later.id


def test_hr_moves_a_typed_schedule_into_a_session(client, db_session, hr_admin, make_job, make_application):
    """A schedule typed before sessions replaced that has no seat; HR moves
    it into a real session, after which it counts like any booking."""
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    instance = _on_exam_stage(db_session, application)
    instance.payload = {"schedule": {"date": "2030-02-01", "time": "08:00", "location": "Old room"}}
    slot = _session(db_session, job, capacity=4)
    hr = auth_headers(client, hr_admin.email)

    profile = client.get(f"/hr/applications/{application.id}/profile", headers=hr).json()
    assert profile["examinations"]["examination"]["schedule_source"] == "typed"
    assert profile["examinations"]["examination"]["open_sessions"] == 1

    resp = client.post(
        f"/hr/applications/{application.id}/exam-booking",
        headers=hr,
        json={"stage_type": "examination", "exam_slot_id": slot.id},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["examinations"]["examination"]["schedule_source"] == "session"


# --- HR edits a session -------------------------------------------------------


def test_editing_a_session_moves_its_bookers_and_tells_them(
    client, db_session, applicant, hr_admin, make_job, make_application
):
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    instance = _on_exam_stage(db_session, application)
    slot = _session(db_session, job, capacity=5)
    _book(client, auth_headers(client, applicant.email), application, slot)
    hr = auth_headers(client, hr_admin.email)
    url = f"/hr/requisitions/{job.id}/exam-slots/{slot.id}"
    before = len(_notices(db_session, applicant))

    # seats alone: nobody needs telling
    resp = client.patch(url, headers=hr, json={"date": "2030-03-01", "start": "09:00", "end": "11:30", "location": "Room 204", "seats": 8})
    assert resp.status_code == 200, resp.text
    assert resp.json()["capacity"] == 8
    assert len(_notices(db_session, applicant)) == before

    resp = client.patch(url, headers=hr, json={"date": "2030-03-08", "start": "13:00", "end": "15:00", "location": "Hall A", "seats": 8})
    assert resp.status_code == 200, resp.text
    db_session.refresh(instance)
    assert instance.payload["schedule"] == {"date": "2030-03-08", "time": "13:00", "end_time": "15:00", "location": "Hall A"}
    latest = _notices(db_session, applicant)[-1]
    assert "has changed" in latest.message and "Fri, 8 Mar 2030, 1:00 PM – 3:00 PM" in latest.message


def test_a_session_edit_is_refused_below_its_bookings_or_into_the_past(
    client, db_session, applicant, hr_admin, make_job, make_application
):
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    _on_exam_stage(db_session, application)
    slot = _session(db_session, job, capacity=2)
    _book(client, auth_headers(client, applicant.email), application, slot)
    hr = auth_headers(client, hr_admin.email)
    url = f"/hr/requisitions/{job.id}/exam-slots/{slot.id}"
    body = {"date": "2030-03-01", "start": "09:00", "end": "11:30", "location": "Room 204"}

    resp = client.patch(url, headers=hr, json={**body, "seats": 0})
    assert resp.status_code == 422
    other_user_seats = {**body, "seats": 1}
    assert client.patch(url, headers=hr, json=other_user_seats).status_code == 200

    resp = client.patch(url, headers=hr, json={**body, "date": "2020-01-01", "seats": 2})
    assert resp.status_code == 422
    resp = client.patch(url, headers=hr, json={**body, "start": "12:00", "end": "11:00", "seats": 2})
    assert resp.status_code == 422


def test_seats_cannot_drop_below_the_number_booked(
    client, db_session, applicant, make_user, hr_admin, make_job, make_application
):
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    _on_exam_stage(db_session, application)
    other_user, other_application = _second_applicant(db_session, make_user, job)
    _on_exam_stage(db_session, other_application)
    slot = _session(db_session, job, capacity=5)
    _book(client, auth_headers(client, applicant.email), application, slot)
    _book(client, auth_headers(client, other_user.email), other_application, slot)

    resp = client.patch(
        f"/hr/requisitions/{job.id}/exam-slots/{slot.id}",
        headers=auth_headers(client, hr_admin.email),
        json={"date": "2030-03-01", "start": "09:00", "end": "11:30", "location": "Room 204", "seats": 1},
    )
    assert resp.status_code == 409
    assert "at least 2 seats" in resp.json()["detail"]


# --- none of these work, and new sessions ------------------------------------


def test_none_of_these_work_reaches_hr_and_new_sessions_reach_the_applicant(
    client, db_session, applicant, hr_admin, make_job, make_application
):
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    _on_exam_stage(db_session, application)
    _session(db_session, job)
    headers = auth_headers(client, applicant.email)

    resp = client.post(
        f"{BOOK.format(application.id)}/none-work",
        headers=headers,
        json={"stage_type": "examination", "note": "I work on weekdays"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["exam_none_work"]["note"] == "I work on weekdays"
    hr_notice = _notices(db_session, hr_admin)[-1]
    assert "none of the Examination sessions" in hr_notice.message and "I work on weekdays" in hr_notice.message

    hr = auth_headers(client, hr_admin.email)
    profile = client.get(f"/hr/applications/{application.id}/profile", headers=hr).json()
    assert profile["examinations"]["examination"]["none_work"]["note"] == "I work on weekdays"

    resp = client.post(
        f"/hr/requisitions/{job.id}/exam-slots/batch",
        headers=hr,
        json={"stage_type": "examination", "dates": ["2030-03-09"], "windows": [{"start": "09:00", "end": "11:30"}], "seats": 10, "location": "Room 204"},
    )
    assert resp.status_code == 201
    assert "New sessions are open" in _notices(db_session, applicant)[-1].message

    # booking answers it
    new_slot = resp.json()["created"][0]["id"]
    resp = client.post(BOOK.format(application.id), headers=headers, json={"stage_type": "examination", "exam_slot_id": new_slot})
    assert resp.json()["exam_none_work"] is None


def test_new_sessions_skip_applicants_who_already_booked(
    client, db_session, applicant, hr_admin, make_job, make_application
):
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    _on_exam_stage(db_session, application)
    slot = _session(db_session, job)
    _book(client, auth_headers(client, applicant.email), application, slot)
    before = len(_notices(db_session, applicant))

    client.post(
        f"/hr/requisitions/{job.id}/exam-slots/batch",
        headers=auth_headers(client, hr_admin.email),
        json={"stage_type": "examination", "dates": ["2030-03-10"], "windows": [{"start": "09:00", "end": "11:30"}], "seats": 10, "location": "Room 204"},
    )
    assert len(_notices(db_session, applicant)) == before


# --- seats follow the application -------------------------------------------


def test_a_closed_application_frees_its_seat_and_reopening_a_full_session_lets_it_go(
    client, db_session, applicant, make_user, hr_admin, make_job, make_application
):
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    instance = _on_exam_stage(db_session, application)
    slot = _session(db_session, job, capacity=1)
    _book(client, auth_headers(client, applicant.email), application, slot)
    hr = auth_headers(client, hr_admin.email)
    seats = lambda: client.get(f"/hr/requisitions/{job.id}/exam-slots", headers=hr).json()[0]["remaining_capacity"]  # noqa: E731
    assert seats() == 0

    resp = client.patch(f"/hr/applications/{application.id}/status", headers=hr, json={"status": "rejected"})
    assert resp.status_code == 200, resp.text
    assert seats() == 1

    # someone else takes the freed seat, then HR reopens the first
    other_user, other_application = _second_applicant(db_session, make_user, job)
    _on_exam_stage(db_session, other_application)
    assert _book(client, auth_headers(client, other_user.email), other_application, slot).status_code == 200

    resp = client.patch(f"/hr/applications/{application.id}/status", headers=hr, json={"status": "active"})
    assert resp.status_code == 200, resp.text
    assert seats() == 0  # not oversold
    db_session.refresh(instance)
    assert "schedule" not in (instance.payload or {})  # picks again


# --- the roster ---------------------------------------------------------------


def test_the_roster_lists_who_booked_each_session(
    client, db_session, applicant, hr_admin, make_job, make_application
):
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    _on_exam_stage(db_session, application)
    booked = _session(db_session, job)
    empty = _session(db_session, job, date="2030-03-02")
    _book(client, auth_headers(client, applicant.email), application, booked)

    sessions = {s["id"]: s for s in client.get(f"/hr/requisitions/{job.id}/exam-slots", headers=auth_headers(client, hr_admin.email)).json()}
    assert [a["applicant_name"] for a in sessions[booked.id]["booked"]] == [applicant.full_name]
    assert sessions[booked.id]["booked"][0]["application_id"] == application.id
    assert sessions[empty.id]["booked"] == []


def test_sessions_belong_to_their_own_exam(client, db_session, applicant, make_job, make_application):
    """A workflow with two exams offers each exam's own sessions only."""
    job = make_job(["document_upload", "examination", "examination_2", "final_decision"])
    application = make_application(job)
    _on_exam_stage(db_session, application)
    own = _session(db_session, job)
    other_exam = _session(db_session, job, stage_type="examination_2")

    detail = client.get(f"/applicant/applications/{application.id}", headers=auth_headers(client, applicant.email)).json()
    assert [s["id"] for s in detail["exam_sessions"]] == [own.id]
    resp = _book(client, auth_headers(client, applicant.email), application, other_exam)
    assert resp.status_code == 404
    assert _exam_instance(db_session, application).stage_type == StageType.examination
