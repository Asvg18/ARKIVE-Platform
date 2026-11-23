"""The evaluator's form waits for a confirmed time (panel revision list,
15 Oct 2026, #13 / step 19c): a scorecard is refused until the applicant
has confirmed the interview time."""

from sqlalchemy import select

from app.models.enums import StageStatus, StageType
from app.models.interview_reschedule_request import InterviewRescheduleRequest
from app.models.notification import Notification
from app.models.requisition_evaluator import RequisitionEvaluator
from app.models.stage_instance import StageInstance
from tests.conftest import auth_headers
from tests.test_evaluator import _all_items

WORKFLOW = ["document_upload", "shortlisting", "interview_round_1", "final_decision"]
SCORECARD = {"item_ratings": _all_items(4), "remarks": "Solid.", "recommendation": "recommended"}


def _round(db_session, make_job, make_application, evaluator):
    job = make_job(WORKFLOW)
    db_session.add(RequisitionEvaluator(requisition_id=job.id, evaluator_id=evaluator.id))
    application = make_application(job)
    application.current_stage = StageType.interview_round_1
    instance = db_session.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.interview_round_1,
        )
    )
    instance.status = StageStatus.in_progress
    instance.assigned_evaluator_id = evaluator.id
    db_session.flush()
    return application, instance


def _evaluate(client, evaluator, instance):
    return client.post(
        f"/evaluator/interviews/{instance.id}/evaluate",
        headers=auth_headers(client, evaluator.email),
        json=SCORECARD,
    )


def _schedule(client, hr_admin, application):
    resp = client.post(
        f"/hr/applications/{application.id}/interview-schedule",
        headers=auth_headers(client, hr_admin.email),
        json={"stage_type": "interview_round_1", "date": "2030-02-01", "time": "10:00", "location": "Room 3"},
    )
    assert resp.status_code == 200, resp.text


def _answer(client, applicant, application, response):
    resp = client.post(
        f"/applicant/applications/{application.id}/schedule-confirmation",
        headers=auth_headers(client, applicant.email),
        json={"stage_type": "interview_round_1", "response": response, "note": ""},
    )
    assert resp.status_code == 200, resp.text


def test_no_time_booked_means_no_scorecard(client, db_session, evaluator, make_job, make_application):
    application, instance = _round(db_session, make_job, make_application, evaluator)
    headers = auth_headers(client, evaluator.email)

    resp = _evaluate(client, evaluator, instance)

    assert resp.status_code == 409
    assert "confirmed" in resp.json()["detail"]
    detail = client.get(f"/evaluator/interviews/{instance.id}", headers=headers).json()
    assert detail["schedule_confirmed"] is False
    queue = client.get("/evaluator/interviews", headers=headers).json()
    assert next(i for i in queue if i["stage_instance_id"] == instance.id)["schedule_confirmed"] is False


def test_the_form_opens_once_the_applicant_confirms(
    client, db_session, evaluator, hr_admin, applicant, make_job, make_application
):
    application, instance = _round(db_session, make_job, make_application, evaluator)
    _schedule(client, hr_admin, application)

    # booked, but not yet answered
    assert _evaluate(client, evaluator, instance).status_code == 409

    _answer(client, applicant, application, "confirmed")

    detail = client.get(f"/evaluator/interviews/{instance.id}", headers=auth_headers(client, evaluator.email)).json()
    assert detail["schedule_confirmed"] is True
    assert _evaluate(client, evaluator, instance).status_code == 200


def test_not_available_keeps_it_locked(
    client, db_session, evaluator, hr_admin, applicant, make_job, make_application
):
    application, instance = _round(db_session, make_job, make_application, evaluator)
    _schedule(client, hr_admin, application)
    _answer(client, applicant, application, "unavailable")

    assert _evaluate(client, evaluator, instance).status_code == 409


def test_a_time_booked_before_confirmations_existed_counts_as_confirmed(
    client, db_session, evaluator, make_job, make_application
):
    """Decided 15 Oct: the old rounds' evaluators aren't stuck."""
    application, instance = _round(db_session, make_job, make_application, evaluator)
    instance.payload = {"schedule": {"date": "2026-09-01", "time": "09:00", "mode": "in_person", "location": "Room 1"}}
    db_session.flush()

    assert _evaluate(client, evaluator, instance).status_code == 200


def test_moving_the_time_asks_the_applicant_again(
    client, db_session, evaluator, hr_admin, applicant, make_job, make_application
):
    """Decided 15 Oct: approving an evaluator's new time re-asks the
    applicant, and tells them, and the form waits for the new answer."""
    application, instance = _round(db_session, make_job, make_application, evaluator)
    instance.payload = {
        "schedule": {"date": "2030-02-01", "time": "10:00", "end_time": "10:45", "mode": "in_person", "location": "Room 3"},
        "schedule_confirmation": {"response": "confirmed", "asked_at": None, "responded_at": None, "note": None},
    }
    request = InterviewRescheduleRequest(
        stage_instance_id=instance.id, requested_by=evaluator.id, proposed_date="2030-02-03", proposed_time="14:00"
    )
    db_session.add(request)
    db_session.flush()

    resp = client.post(
        f"/hr/applications/{application.id}/reschedule-requests/{request.id}/resolve",
        headers=auth_headers(client, hr_admin.email),
        json={"decision": "approve", "date": "2030-02-03", "time": "14:00"},
    )

    assert resp.status_code == 200, resp.text
    db_session.refresh(instance)
    assert instance.payload["schedule"]["date"] == "2030-02-03"
    # the old slot's end no longer applies to the new time
    assert "end_time" not in instance.payload["schedule"]
    assert instance.payload["schedule_confirmation"]["response"] is None
    notice = db_session.scalar(
        select(Notification).where(Notification.user_id == applicant.id, Notification.kind == "schedule")
    )
    assert "Please confirm you can attend" in notice.message
    assert _evaluate(client, evaluator, instance).status_code == 409

    _answer(client, applicant, application, "confirmed")
    assert _evaluate(client, evaluator, instance).status_code == 200
