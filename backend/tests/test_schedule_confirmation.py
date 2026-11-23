"""The confirmation an applicant gives against a scheduled interview.

The applicant confirms the time HR booked, so a clash surfaces before
the day rather than as an empty chair. What these tests are most
careful about is the distinction that makes this
worth having -- "I can't make that time" is not "I'm out", and nothing
here may quietly turn one into the other.
"""

from app.models.enums import ApplicationStatus, StageType
from app.models.notification import Notification
from app.models.stage_instance import StageInstance
from app.services import schedule_confirmation
from tests.conftest import auth_headers

WORKFLOW = ["document_upload", "interview_round_1", "final_decision"]


def _schedule(client, application, hr_headers, *, date="2027-06-01", time="10:00"):
    return client.post(
        f"/hr/applications/{application.id}/interview-schedule",
        json={
            "stage_type": "interview_round_1",
            "date": date,
            "time": time,
            "mode": "in_person",
            "location": "Room 4",
        },
        headers=hr_headers,
    )


def _payload(db_session, application) -> dict:
    return (
        db_session.query(StageInstance)
        .filter(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.interview_round_1,
        )
        .one()
        .payload
        or {}
    )


def test_scheduling_an_interview_asks_the_applicant_to_confirm(
    client, db_session, hr_admin, applicant, make_job, make_application, monkeypatch
):
    sent: list[dict] = []
    monkeypatch.setattr(
        "app.api.hr.common.send_email_safely",
        lambda **kwargs: sent.append(kwargs) or True,
    )
    job = make_job(WORKFLOW, title="Confirmable Interview")
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = _schedule(client, application, hr_headers)

    assert resp.status_code == 200, resp.text
    confirmation = _payload(db_session, application)["schedule_confirmation"]
    assert confirmation["response"] is None

    # the letter tells them it is waiting, which is the whole point of
    # asking somebody who is not sitting in the app right now
    assert len(sent) == 1
    assert "confirmation is waiting in your ARKIVE account" in sent[0]["body"]


def test_the_applicant_can_confirm_they_are_available(
    client, db_session, hr_admin, applicant, make_job, make_application, monkeypatch
):
    monkeypatch.setattr("app.api.hr.common.send_email_safely", lambda **kwargs: True)
    job = make_job(WORKFLOW, title="Confirmed Interview")
    application = make_application(job)
    db_session.flush()
    _schedule(client, application, auth_headers(client, "hr-test@arkivetesting.com"))
    headers = auth_headers(client, "applicant-test@arkivetesting.com")

    resp = client.post(
        f"/applicant/applications/{application.id}/schedule-confirmation",
        json={"stage_type": "interview_round_1", "response": "confirmed"},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    assert _payload(db_session, application)["schedule_confirmation"]["response"] == "confirmed"


def test_saying_unavailable_tells_hr_and_does_not_withdraw_the_application(
    client, db_session, hr_admin, applicant, make_job, make_application, monkeypatch
):
    """The distinction this feature exists for. A clash is a scheduling
    problem, not a candidate dropping out."""
    monkeypatch.setattr("app.api.hr.common.send_email_safely", lambda **kwargs: True)
    job = make_job(WORKFLOW, title="Clashing Interview")
    application = make_application(job)
    db_session.flush()
    _schedule(client, application, auth_headers(client, "hr-test@arkivetesting.com"))
    headers = auth_headers(client, "applicant-test@arkivetesting.com")

    resp = client.post(
        f"/applicant/applications/{application.id}/schedule-confirmation",
        json={
            "stage_type": "interview_round_1",
            "response": "unavailable",
            "note": "I have a class that morning.",
        },
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    confirmation = _payload(db_session, application)["schedule_confirmation"]
    assert confirmation["response"] == "unavailable"
    assert confirmation["note"] == "I have a class that morning."

    # still in the running
    db_session.refresh(application)
    assert application.status == ApplicationStatus.active

    # and HR actually hears about it, with what the candidate said
    messages = [
        n.message
        for n in db_session.query(Notification).filter(Notification.user_id == hr_admin.id)
    ]
    assert any("not available" in m and "I have a class that morning." in m for m in messages)


def test_rescheduling_asks_again(
    client, db_session, hr_admin, applicant, make_job, make_application, monkeypatch
):
    """A yes against last week's slot says nothing about this week's. The
    old answer must not carry over, or HR would read a confirmation for a
    time that no longer exists."""
    monkeypatch.setattr("app.api.hr.common.send_email_safely", lambda **kwargs: True)
    job = make_job(WORKFLOW, title="Moved Interview")
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    _schedule(client, application, hr_headers)
    client.post(
        f"/applicant/applications/{application.id}/schedule-confirmation",
        json={"stage_type": "interview_round_1", "response": "confirmed"},
        headers=auth_headers(client, "applicant-test@arkivetesting.com"),
    )
    assert _payload(db_session, application)["schedule_confirmation"]["response"] == "confirmed"

    _schedule(client, application, hr_headers, date="2027-06-08", time="14:00")

    assert _payload(db_session, application)["schedule_confirmation"]["response"] is None


def test_answering_twice_is_refused(
    client, db_session, hr_admin, applicant, make_job, make_application, monkeypatch
):
    monkeypatch.setattr("app.api.hr.common.send_email_safely", lambda **kwargs: True)
    job = make_job(WORKFLOW, title="Answer Once")
    application = make_application(job)
    db_session.flush()
    _schedule(client, application, auth_headers(client, "hr-test@arkivetesting.com"))
    headers = auth_headers(client, "applicant-test@arkivetesting.com")
    body = {"stage_type": "interview_round_1", "response": "confirmed"}
    client.post(f"/applicant/applications/{application.id}/schedule-confirmation", json=body, headers=headers)

    resp = client.post(
        f"/applicant/applications/{application.id}/schedule-confirmation", json=body, headers=headers
    )

    assert resp.status_code == 409, resp.text
    assert "already answered" in resp.json()["detail"]


def test_confirming_an_unscheduled_stage_is_refused(
    client, db_session, hr_admin, applicant, make_job, make_application
):
    job = make_job(WORKFLOW, title="Not Scheduled Yet")
    application = make_application(job)
    db_session.flush()
    headers = auth_headers(client, "applicant-test@arkivetesting.com")

    resp = client.post(
        f"/applicant/applications/{application.id}/schedule-confirmation",
        json={"stage_type": "interview_round_1", "response": "confirmed"},
        headers=headers,
    )

    assert resp.status_code == 409, resp.text
    assert "not been scheduled" in resp.json()["detail"]


def test_an_applicant_cannot_confirm_someone_elses_interview(
    client, db_session, hr_admin, applicant, make_user, make_job, make_application, monkeypatch
):
    from app.models.enums import UserRole

    monkeypatch.setattr("app.api.hr.common.send_email_safely", lambda **kwargs: True)
    job = make_job(WORKFLOW, title="Someone Elses")
    application = make_application(job)
    db_session.flush()
    _schedule(client, application, auth_headers(client, "hr-test@arkivetesting.com"))
    make_user("intruder@arkivetesting.com", UserRole.applicant)
    headers = auth_headers(client, "intruder@arkivetesting.com")

    resp = client.post(
        f"/applicant/applications/{application.id}/schedule-confirmation",
        json={"stage_type": "interview_round_1", "response": "confirmed"},
        headers=headers,
    )

    # 404, not 403 -- the same never-confirm-an-application-exists rule
    # every other applicant route follows
    assert resp.status_code == 404, resp.text


def test_the_confirmation_is_visible_to_the_applicant_but_the_evaluation_is_not(
    client, db_session, hr_admin, applicant, make_job, make_application, monkeypatch
):
    """The payload allow-list had to be widened to let this through, so
    pin that it did not let anything else out with it."""
    monkeypatch.setattr("app.api.hr.common.send_email_safely", lambda **kwargs: True)
    job = make_job(WORKFLOW, title="Allow List")
    application = make_application(job)
    db_session.flush()
    _schedule(client, application, auth_headers(client, "hr-test@arkivetesting.com"))

    instance = (
        db_session.query(StageInstance)
        .filter(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.interview_round_1,
        )
        .one()
    )
    instance.payload = {**(instance.payload or {}), "evaluation": {"remarks": "private"}}
    db_session.flush()
    headers = auth_headers(client, "applicant-test@arkivetesting.com")

    detail = client.get(f"/applicant/applications/{application.id}", headers=headers).json()
    payload = next(
        s["payload"] for s in detail["stage_instances"] if s["stage_type"] == "interview_round_1"
    )

    assert "schedule_confirmation" in payload
    assert "schedule" in payload
    assert "evaluation" not in payload


def test_the_service_records_what_was_asked_and_when(db_session, make_job, make_application):
    """Unit-level: open_confirmation is deliberately not idempotent, so a
    re-ask always produces a fresh, unanswered block."""
    job = make_job(WORKFLOW)
    application = make_application(job)
    db_session.flush()
    instance = (
        db_session.query(StageInstance)
        .filter(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.interview_round_1,
        )
        .one()
    )
    instance.payload = {"schedule": {"date": "2027-06-01", "time": "10:00"}}

    first = schedule_confirmation.open_confirmation(instance)
    assert first["response"] is None and first["asked_at"]

    schedule_confirmation.respond(db_session, instance=instance, response="confirmed")
    assert schedule_confirmation.read_confirmation(instance)["response"] == "confirmed"

    second = schedule_confirmation.open_confirmation(instance)
    assert second["response"] is None
    assert schedule_confirmation.read_confirmation(instance)["responded_at"] is None
