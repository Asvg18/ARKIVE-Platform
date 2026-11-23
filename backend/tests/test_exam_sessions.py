"""Exam sessions (panel revisions, 15-16 Oct 2026): HR adds a job's
sessions in one go (dates × time windows × seats); every applicant on the
exam books one with a free seat and can change it until 24 hours before;
HR can book or move anyone, edit a session (its bookers are told) and see
who booked each; "none of these work" reaches HR; and a booking is the
only way an exam gets a time."""

from sqlalchemy import select

from app.models.agent_run import AgentRun
from app.models.enums import ExamBookingStatus, StageStatus, StageType
from app.models.exam_slot import ExamSlot
from app.models.exam_slot_booking import ExamSlotBooking
from app.models.notification import Notification
from app.models.stage_instance import StageInstance
from tests.conftest import auth_headers

EXAM_WORKFLOW = ["document_upload", "examination", "final_decision"]


def _batch(**overrides) -> dict:
    body = {
        "stage_type": "examination",
        "dates": ["2030-03-01"],
        "windows": [{"start": "09:00", "end": "11:30"}],
        "seats": 20,
        "location": "Room 204",
    }
    body.update(overrides)
    return body


def _session(db_session, job, **overrides) -> ExamSlot:
    fields = {
        "requisition_id": job.id,
        "stage_type": "examination",
        "date": "2030-03-01",
        "time": "09:00",
        "end_time": "11:30",
        "location": "Room 204",
        "capacity": 20,
    }
    fields.update(overrides)
    slot = ExamSlot(**fields)
    db_session.add(slot)
    db_session.flush()
    return slot


def _exam_instance(db_session, application) -> StageInstance:
    return db_session.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.examination,
        )
    )


def _on_exam_stage(db_session, application) -> StageInstance:
    application.current_stage = StageType.examination
    instance = _exam_instance(db_session, application)
    instance.status = StageStatus.in_progress
    db_session.flush()
    return instance


# --- HR: Add sessions ------------------------------------------------------


def test_add_sessions_creates_every_date_and_window(client, hr_admin, make_job):
    job = make_job(EXAM_WORKFLOW)
    headers = auth_headers(client, hr_admin.email)

    resp = client.post(
        f"/hr/requisitions/{job.id}/exam-slots/batch",
        headers=headers,
        json=_batch(
            dates=["2030-03-02", "2030-03-01"],
            windows=[{"start": "13:00", "end": "16:30"}, {"start": "09:00", "end": "11:30"}],
            location="  Room 204 ",
        ),
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["skipped"] == 0
    sessions = resp.json()["created"]
    assert [(s["date"], s["time"], s["end_time"]) for s in sessions] == [
        ("2030-03-01", "09:00", "11:30"),
        ("2030-03-01", "13:00", "16:30"),
        ("2030-03-02", "09:00", "11:30"),
        ("2030-03-02", "13:00", "16:30"),
    ]
    assert all(s["capacity"] == 20 and s["remaining_capacity"] == 20 for s in sessions)
    assert {s["location"] for s in sessions} == {"Room 204"}
    listed = client.get(f"/hr/requisitions/{job.id}/exam-slots", headers=headers).json()
    assert len(listed) == 4


def test_add_sessions_refuses_bad_batches(client, hr_admin, make_job):
    job = make_job(EXAM_WORKFLOW)
    headers = auth_headers(client, hr_admin.email)
    url = f"/hr/requisitions/{job.id}/exam-slots/batch"

    for body in (
        _batch(dates=["2020-01-01"]),
        _batch(dates=["2030-03-01", "2030-03-01"]),
        _batch(windows=[{"start": "11:30", "end": "09:00"}]),
        _batch(windows=[{"start": "09:00", "end": "11:30"}, {"start": "11:00", "end": "12:00"}]),
        _batch(location="   "),
        _batch(seats=0),
        _batch(dates=[]),
        _batch(stage_type="final_decision"),
    ):
        assert client.post(url, headers=headers, json=body).status_code == 422, body

    # an exam stage this job doesn't use
    resp = client.post(url, headers=headers, json=_batch(stage_type="examination_2"))
    assert resp.status_code == 422
    assert client.get(f"/hr/requisitions/{job.id}/exam-slots", headers=headers).json() == []


def test_add_sessions_skips_a_session_the_job_already_has(client, db_session, hr_admin, make_job):
    """Same exam, date, time and place (case aside) is left out and
    counted, rather than refusing the whole batch (16 Oct 2026)."""
    job = make_job(EXAM_WORKFLOW)
    _session(db_session, job, date="2030-03-02")
    headers = auth_headers(client, hr_admin.email)

    resp = client.post(
        f"/hr/requisitions/{job.id}/exam-slots/batch",
        headers=headers,
        json=_batch(dates=["2030-03-01", "2030-03-02"], location="room 204"),
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["skipped"] == 1
    assert [s["date"] for s in resp.json()["created"]] == ["2030-03-01"]
    assert len(client.get(f"/hr/requisitions/{job.id}/exam-slots", headers=headers).json()) == 2


def test_a_booked_session_cannot_be_deleted(client, db_session, hr_admin, make_job, make_application):
    """Only a session nobody has booked can go -- an old pending proposal
    holds its seat too."""
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    instance = _exam_instance(db_session, application)
    slot = _session(db_session, job)
    booking = ExamSlotBooking(
        exam_slot_id=slot.id,
        application_id=application.id,
        stage_instance_id=instance.id,
        applicant_selected_slot_ids=[slot.id],
    )
    db_session.add(booking)
    db_session.flush()
    headers = auth_headers(client, hr_admin.email)
    url = f"/hr/requisitions/{job.id}/exam-slots/{slot.id}"

    resp = client.delete(url, headers=headers)
    assert resp.status_code == 409
    assert resp.json()["detail"].startswith("Someone has booked this session, so it can't be deleted.")

    booking.status = ExamBookingStatus.denied
    db_session.flush()
    assert client.delete(url, headers=headers).status_code == 204


# --- Applicant: pick a session in the Examination stage -------------------


def test_applicant_is_offered_open_sessions_only_on_the_exam_stage(
    client, db_session, applicant, make_job, make_application
):
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    open_one = _session(db_session, job, date="2030-03-01")
    _session(db_session, job, date="2020-01-01")  # already happened
    _session(db_session, job, date="2030-03-02", capacity=0)  # full
    headers = auth_headers(client, applicant.email)
    url = f"/applicant/applications/{application.id}"

    # still on Document Upload -- nothing to pick yet
    assert client.get(url, headers=headers).json()["exam_sessions"] == []

    _on_exam_stage(db_session, application)
    sessions = client.get(url, headers=headers).json()["exam_sessions"]
    assert [s["id"] for s in sessions] == [open_one.id]
    assert sessions[0]["end_time"] == "11:30"
    assert sessions[0]["remaining_capacity"] == 20


def test_booking_a_session_schedules_the_exam_at_once(
    client, db_session, applicant, make_job, make_application
):
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    instance = _on_exam_stage(db_session, application)
    slot = _session(db_session, job)
    headers = auth_headers(client, applicant.email)

    resp = client.post(
        f"/applicant/applications/{application.id}/exam-booking",
        headers=headers,
        json={"stage_type": "examination", "exam_slot_id": slot.id},
    )

    assert resp.status_code == 200, resp.text
    detail = resp.json()
    exam = next(s for s in detail["stage_instances"] if s["stage_type"] == "examination")
    assert exam["payload"]["schedule"] == {
        "date": "2030-03-01",
        "time": "09:00",
        "end_time": "11:30",
        "location": "Room 204",
    }
    # scheduled now, so nothing left to pick
    assert detail["exam_sessions"] == []

    booking = db_session.scalar(select(ExamSlotBooking).where(ExamSlotBooking.stage_instance_id == instance.id))
    assert booking.status == ExamBookingStatus.approved
    assert booking.exam_slot_id == slot.id
    assert db_session.scalar(
        select(AgentRun).where(
            AgentRun.application_id == application.id, AgentRun.agent_name == "exam_scheduling_agent"
        )
    ) is not None
    notice = db_session.scalar(select(Notification).where(Notification.user_id == applicant.id))
    assert notice.kind == "schedule"
    assert "Fri, 1 Mar 2030, 9:00 AM – 11:30 AM" in notice.message


def test_an_applicant_cannot_book_twice(client, db_session, applicant, make_job, make_application):
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    _on_exam_stage(db_session, application)
    first = _session(db_session, job)
    second = _session(db_session, job, date="2030-03-02")
    headers = auth_headers(client, applicant.email)
    url = f"/applicant/applications/{application.id}/exam-booking"

    assert client.post(url, headers=headers, json={"stage_type": "examination", "exam_slot_id": first.id}).status_code == 200
    resp = client.post(url, headers=headers, json={"stage_type": "examination", "exam_slot_id": second.id})
    assert resp.status_code == 409
    assert "already booked" in resp.json()["detail"]


def test_a_full_or_past_session_cannot_be_booked(client, db_session, applicant, make_job, make_application):
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    _on_exam_stage(db_session, application)
    full = _session(db_session, job, capacity=0)
    past = _session(db_session, job, date="2020-01-01")
    headers = auth_headers(client, applicant.email)
    url = f"/applicant/applications/{application.id}/exam-booking"

    resp = client.post(url, headers=headers, json={"stage_type": "examination", "exam_slot_id": full.id})
    assert resp.status_code == 409
    assert "filled up" in resp.json()["detail"]
    resp = client.post(url, headers=headers, json={"stage_type": "examination", "exam_slot_id": past.id})
    assert resp.status_code == 409
    assert "already started" in resp.json()["detail"]


def test_booking_only_on_the_exam_stage_and_only_this_jobs_sessions(
    client, db_session, applicant, make_job, make_application
):
    job = make_job(EXAM_WORKFLOW)
    other_job = make_job(EXAM_WORKFLOW, title="Other Job")
    application = make_application(job)
    slot = _session(db_session, job)
    elsewhere = _session(db_session, other_job)
    headers = auth_headers(client, applicant.email)
    url = f"/applicant/applications/{application.id}/exam-booking"

    # still on Document Upload
    resp = client.post(url, headers=headers, json={"stage_type": "examination", "exam_slot_id": slot.id})
    assert resp.status_code == 409

    _on_exam_stage(db_session, application)
    resp = client.post(url, headers=headers, json={"stage_type": "examination", "exam_slot_id": elsewhere.id})
    assert resp.status_code == 404


def test_hr_moves_a_booked_candidate_and_the_seat_follows(
    client, db_session, applicant, hr_admin, make_job, make_application
):
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    _on_exam_stage(db_session, application)
    first = _session(db_session, job, capacity=5)
    second = _session(db_session, job, date="2030-04-01", location="Room 9", capacity=5)
    client.post(
        f"/applicant/applications/{application.id}/exam-booking",
        headers=auth_headers(client, applicant.email),
        json={"stage_type": "examination", "exam_slot_id": first.id},
    )
    hr_headers = auth_headers(client, hr_admin.email)

    resp = client.post(
        f"/hr/applications/{application.id}/exam-booking",
        headers=hr_headers,
        json={"stage_type": "examination", "exam_slot_id": second.id},
    )

    assert resp.status_code == 200, resp.text
    entry = resp.json()["examinations"]["examination"]
    assert entry["schedule_source"] == "session"
    assert entry["booked_slot_id"] == second.id
    assert entry["schedule"]["location"] == "Room 9"
    seats = {s["id"]: s["remaining_capacity"] for s in client.get(f"/hr/requisitions/{job.id}/exam-slots", headers=hr_headers).json()}
    assert seats == {first.id: 5, second.id: 4}
    notices = db_session.scalars(select(Notification).where(Notification.user_id == applicant.id)).all()
    assert any(n.message.startswith("HR moved your Examination to Mon, 1 Apr 2030") for n in notices)


# --- HR: Enter Score records the date taken --------------------------------


def test_exam_score_records_the_date_taken(client, db_session, applicant, hr_admin, make_job, make_application):
    job = make_job(EXAM_WORKFLOW)
    application = make_application(job)
    instance = _on_exam_stage(db_session, application)
    instance.payload = {"schedule": {"date": "2026-10-01", "time": "09:00", "location": "Room 204"}}
    db_session.flush()
    headers = auth_headers(client, hr_admin.email)
    url = f"/hr/applications/{application.id}/examination-result"

    # left out: the booked session's date
    resp = client.patch(url, headers=headers, json={"stage_type": "examination", "score": 88})
    assert resp.status_code == 200, resp.text
    assert resp.json()["examinations"]["examination"]["taken_on"] == "2026-10-01"

    # HR's own date wins
    resp = client.patch(url, headers=headers, json={"stage_type": "examination", "score": 88, "taken_on": "2026-10-02"})
    assert resp.json()["examinations"]["examination"]["taken_on"] == "2026-10-02"

    # a day that hasn't happened yet is refused
    resp = client.patch(url, headers=headers, json={"stage_type": "examination", "score": 88, "taken_on": "2099-01-01"})
    assert resp.status_code == 422


def test_hrs_next_step_before_an_exam_is_open_sessions_and_the_score(client, hr_admin, make_job, make_application):
    """The applicant books the session themselves, so the profile's next
    step tells HR to keep sessions open and record the score, not to
    schedule the exam, and it names the exam as the job calls it."""
    headers = auth_headers(client, hr_admin.email)

    plain = make_application(make_job(EXAM_WORKFLOW, title="Plain Exam"))
    profile = client.get(f"/hr/applications/{plain.id}/profile", headers=headers).json()
    assert profile["next_steps"] == "Make sure Examination has open sessions, then record the score."

    job = make_job(["document_upload", "examination_1", "final_decision"], title="Named Exam")
    job.examination_labels = {"examination_1": "Written Test"}
    named = make_application(job)
    profile = client.get(f"/hr/applications/{named.id}/profile", headers=headers).json()
    assert profile["next_steps"] == "Make sure Written Test has open sessions, then record the score."
