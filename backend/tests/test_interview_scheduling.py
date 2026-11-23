"""Interview scheduling, evaluator → HR → applicant (panel revision list,
15 Oct 2026, step 19b): the evaluator enters free ranges, HR sends the
slots it keeps, the applicant picks one -- which confirms it -- and a
slot taken by one candidate disappears for every other candidate of the
same evaluator."""

from sqlalchemy import select

from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus, StageStatus, StageType, UserRole
from app.models.interview_availability import InterviewAvailability
from app.models.notification import Notification
from app.models.requisition_evaluator import RequisitionEvaluator
from app.models.stage_instance import StageInstance
from app.services.applications import create_application_with_stage_instances
from tests.conftest import auth_headers

WORKFLOW = ["document_upload", "shortlisting", "interview_round_1", "final_decision"]
DAY = "2030-03-04"


def _interview_instance(db_session, application) -> StageInstance:
    return db_session.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.interview_round_1,
        )
    )


def _on_interview(db_session, application, evaluator) -> StageInstance:
    application.current_stage = StageType.interview_round_1
    instance = _interview_instance(db_session, application)
    instance.status = StageStatus.in_progress
    instance.assigned_evaluator_id = evaluator.id
    db_session.flush()
    return instance


def _job(make_job, db_session, evaluator, title="Interview Job"):
    job = make_job(WORKFLOW, title=title)
    job.interview_durations = {"interview_round_1": 45}
    db_session.add(RequisitionEvaluator(requisition_id=job.id, evaluator_id=evaluator.id))
    db_session.flush()
    return job


def _save_times(client, headers, instance, windows):
    return client.put(
        f"/evaluator/interviews/{instance.id}/availability",
        headers=headers,
        json={"windows": [{"date": d, "start": s, "end": e} for d, s, e in windows]},
    )


def _send(client, headers, application, starts, **where):
    body = {
        "stage_type": "interview_round_1",
        "slots": [{"date": DAY, "time": t} for t in starts],
        "mode": "in_person",
        "location": "HR Office, Room 2",
    }
    body.update(where)
    return client.post(f"/hr/applications/{application.id}/interview-slots", headers=headers, json=body)


def _profile_round(client, headers, application):
    profile = client.get(f"/hr/applications/{application.id}/profile", headers=headers).json()
    return profile["interview_ratings"]["interview_round_1"]


# --- evaluator: My availability --------------------------------------------


def test_evaluator_saves_free_ranges_and_hr_is_told(
    client, db_session, evaluator, hr_admin, make_job, make_application
):
    job = _job(make_job, db_session, evaluator)
    application = make_application(job)
    instance = _on_interview(db_session, application, evaluator)
    headers = auth_headers(client, evaluator.email)

    resp = _save_times(client, headers, instance, [(DAY, "09:00", "11:15"), (DAY, "13:00", "14:00")])

    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["duration_minutes"] == 45
    assert [(w["start"], w["end"]) for w in detail["availability"]] == [("09:00", "11:15"), ("13:00", "14:00")]
    notice = db_session.scalar(select(Notification).where(Notification.user_id == hr_admin.id))
    assert notice is not None and notice.kind == "schedule"
    assert "free times" in notice.message

    # saving again replaces the set
    resp = _save_times(client, headers, instance, [(DAY, "10:00", "11:00")])
    assert [(w["start"], w["end"]) for w in resp.json()["availability"]] == [("10:00", "11:00")]


def test_bad_ranges_are_refused(client, db_session, evaluator, make_job, make_application):
    job = _job(make_job, db_session, evaluator)
    application = make_application(job)
    instance = _on_interview(db_session, application, evaluator)
    headers = auth_headers(client, evaluator.email)

    assert _save_times(client, headers, instance, [("2020-01-01", "09:00", "10:00")]).status_code == 422
    assert _save_times(client, headers, instance, [(DAY, "11:00", "09:00")]).status_code == 422
    assert _save_times(client, headers, instance, [(DAY, "09:00", "11:00"), (DAY, "10:30", "12:00")]).status_code == 422
    # shorter than one 45-minute interview
    resp = _save_times(client, headers, instance, [(DAY, "09:00", "09:30")])
    assert resp.status_code == 422
    assert "45 minutes" in resp.json()["detail"]


def test_an_evaluator_cannot_set_times_on_someone_elses_round(
    client, db_session, evaluator, make_user, make_job, make_application
):
    job = _job(make_job, db_session, evaluator)
    application = make_application(job)
    instance = _on_interview(db_session, application, evaluator)
    other = make_user("other-evaluator@arkivetesting.com", UserRole.evaluator)

    resp = _save_times(client, auth_headers(client, other.email), instance, [(DAY, "09:00", "10:00")])
    assert resp.status_code == 404


# --- HR: cut into slots, untick, send ----------------------------------------


def test_hr_sees_the_ranges_cut_into_slots_of_the_round_length(
    client, db_session, evaluator, hr_admin, make_job, make_application
):
    job = _job(make_job, db_session, evaluator)
    application = make_application(job)
    instance = _on_interview(db_session, application, evaluator)
    _save_times(client, auth_headers(client, evaluator.email), instance, [(DAY, "09:00", "11:15")])

    entry = _profile_round(client, auth_headers(client, hr_admin.email), application)

    assert entry["duration_minutes"] == 45
    assert [(s["time"], s["end_time"], s["taken"]) for s in entry["slot_choices"]] == [
        ("09:00", "09:45", False),
        ("09:45", "10:30", False),
        ("10:30", "11:15", False),
    ]
    assert entry["slot_offer"] is None


def test_hr_sends_the_ticked_slots_and_the_applicant_sees_only_those(
    client, db_session, evaluator, hr_admin, applicant, make_job, make_application
):
    job = _job(make_job, db_session, evaluator)
    application = make_application(job)
    instance = _on_interview(db_session, application, evaluator)
    _save_times(client, auth_headers(client, evaluator.email), instance, [(DAY, "09:00", "11:15")])
    hr_headers = auth_headers(client, hr_admin.email)

    resp = _send(client, hr_headers, application, ["09:00", "10:30"])

    assert resp.status_code == 200, resp.text
    offer = resp.json()["interview_ratings"]["interview_round_1"]["slot_offer"]
    assert [s["time"] for s in offer["slots"]] == ["09:00", "10:30"]
    assert offer["duration_minutes"] == 45
    assert offer["location"] == "HR Office, Room 2"

    detail = client.get(f"/applicant/applications/{application.id}", headers=auth_headers(client, applicant.email)).json()
    sent = detail["interview_slot_offer"]
    assert [(s["time"], s["end_time"]) for s in sent["slots"]] == [("09:00", "09:45"), ("10:30", "11:15")]
    assert sent["mode"] == "in_person"
    notice = db_session.scalar(select(Notification).where(Notification.user_id == applicant.id))
    assert notice.message.startswith("Pick a time for your")


def test_hr_cannot_send_a_time_outside_the_evaluators_ranges(
    client, db_session, evaluator, hr_admin, make_job, make_application
):
    job = _job(make_job, db_session, evaluator)
    application = make_application(job)
    instance = _on_interview(db_session, application, evaluator)
    _save_times(client, auth_headers(client, evaluator.email), instance, [(DAY, "09:00", "11:15")])
    hr_headers = auth_headers(client, hr_admin.email)

    assert _send(client, hr_headers, application, ["09:15"]).status_code == 409
    assert _send(client, hr_headers, application, ["14:00"]).status_code == 409
    assert _send(client, hr_headers, application, ["09:00"], location=" ").status_code == 422
    assert _send(client, hr_headers, application, ["09:00"], mode="online", meeting_link="meet").status_code == 422


# --- applicant: pick = confirm -----------------------------------------------


def test_picking_a_slot_books_and_confirms_it(
    client, db_session, evaluator, hr_admin, applicant, make_job, make_application
):
    job = _job(make_job, db_session, evaluator)
    application = make_application(job)
    instance = _on_interview(db_session, application, evaluator)
    _save_times(client, auth_headers(client, evaluator.email), instance, [(DAY, "09:00", "11:15")])
    _send(client, auth_headers(client, hr_admin.email), application, ["09:00", "09:45"])
    headers = auth_headers(client, applicant.email)
    url = f"/applicant/applications/{application.id}/interview-slot"

    resp = client.post(url, headers=headers, json={"stage_type": "interview_round_1", "date": DAY, "time": "09:45"})

    assert resp.status_code == 200, resp.text
    detail = resp.json()
    stage = next(s for s in detail["stage_instances"] if s["stage_type"] == "interview_round_1")
    assert stage["payload"]["schedule"] == {
        "date": DAY,
        "time": "09:45",
        "end_time": "10:30",
        "mode": "in_person",
        "location": "HR Office, Room 2",
        "meeting_link": None,
    }
    assert stage["payload"]["schedule_confirmation"]["response"] == "confirmed"
    assert detail["interview_slot_offer"] is None
    notice = db_session.scalar(select(Notification).where(Notification.user_id == evaluator.id))
    assert "picked" in notice.message

    # nothing left to pick
    again = client.post(url, headers=headers, json={"stage_type": "interview_round_1", "date": DAY, "time": "09:00"})
    assert again.status_code == 409


def test_a_slot_taken_by_one_candidate_disappears_for_the_same_evaluators_others(
    client, db_session, evaluator, hr_admin, applicant, make_user, make_job, make_application
):
    """Across jobs, too: it is the evaluator's time that is taken."""
    job = _job(make_job, db_session, evaluator)
    other_job = _job(make_job, db_session, evaluator, title="Another Interview Job")
    first = make_application(job)
    first_round = _on_interview(db_session, first, evaluator)
    other_applicant = make_user("second-applicant@arkivetesting.com", UserRole.applicant)
    second = create_application_with_stage_instances(db_session, applicant_id=other_applicant.id, requisition=other_job)
    second_round = _on_interview(db_session, second, evaluator)
    evaluator_headers = auth_headers(client, evaluator.email)
    hr_headers = auth_headers(client, hr_admin.email)
    for round_ in (first_round, second_round):
        _save_times(client, evaluator_headers, round_, [(DAY, "09:00", "10:30")])
    _send(client, hr_headers, first, ["09:00", "09:45"])
    _send(client, hr_headers, second, ["09:00", "09:45"])

    client.post(
        f"/applicant/applications/{first.id}/interview-slot",
        headers=auth_headers(client, applicant.email),
        json={"stage_type": "interview_round_1", "date": DAY, "time": "09:00"},
    )

    second_headers = auth_headers(client, other_applicant.email)
    offer = client.get(f"/applicant/applications/{second.id}", headers=second_headers).json()["interview_slot_offer"]
    assert [s["time"] for s in offer["slots"]] == ["09:45"]
    taken = client.post(
        f"/applicant/applications/{second.id}/interview-slot",
        headers=second_headers,
        json={"stage_type": "interview_round_1", "date": DAY, "time": "09:00"},
    )
    assert taken.status_code == 409
    # HR sees it marked taken, and can't send it again
    choices = _profile_round(client, hr_headers, second)["slot_choices"]
    assert [(c["time"], c["taken"]) for c in choices] == [("09:00", True), ("09:45", False)]
    assert _send(client, hr_headers, second, ["09:00"]).status_code == 409

    # a candidate who leaves gives the time back
    first.status = ApplicationStatus.withdrawn
    db_session.flush()
    choices = _profile_round(client, hr_headers, second)["slot_choices"]
    assert [(c["time"], c["taken"]) for c in choices] == [("09:00", False), ("09:45", False)]


def test_none_of_these_work_tells_hr(
    client, db_session, evaluator, hr_admin, applicant, make_job, make_application
):
    job = _job(make_job, db_session, evaluator)
    application = make_application(job)
    instance = _on_interview(db_session, application, evaluator)
    _save_times(client, auth_headers(client, evaluator.email), instance, [(DAY, "09:00", "11:15")])
    hr_headers = auth_headers(client, hr_admin.email)
    _send(client, hr_headers, application, ["09:00"])

    resp = client.post(
        f"/applicant/applications/{application.id}/interview-slot/decline",
        headers=auth_headers(client, applicant.email),
        json={"stage_type": "interview_round_1", "note": "Mornings are classes"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["interview_slot_offer"]["response"] == "none_work"
    assert resp.json()["status"] == "active"
    notice = db_session.scalar(
        select(Notification).where(Notification.user_id == hr_admin.id, Notification.message.like("None of the times%"))
    )
    assert "Mornings are classes" in notice.message
    assert _profile_round(client, hr_headers, application)["slot_offer"]["response"] == "none_work"

    # HR sends others, and the question is open again
    _send(client, hr_headers, application, ["10:30"])
    offer = client.get(
        f"/applicant/applications/{application.id}", headers=auth_headers(client, applicant.email)
    ).json()["interview_slot_offer"]
    assert offer["response"] is None
    assert [s["time"] for s in offer["slots"]] == ["10:30"]


def test_sending_again_replaces_a_booked_time(
    client, db_session, evaluator, hr_admin, applicant, make_job, make_application
):
    job = _job(make_job, db_session, evaluator)
    application = make_application(job)
    instance = _on_interview(db_session, application, evaluator)
    _save_times(client, auth_headers(client, evaluator.email), instance, [(DAY, "09:00", "11:15")])
    hr_headers = auth_headers(client, hr_admin.email)
    _send(client, hr_headers, application, ["09:00"])
    client.post(
        f"/applicant/applications/{application.id}/interview-slot",
        headers=auth_headers(client, applicant.email),
        json={"stage_type": "interview_round_1", "date": DAY, "time": "09:00"},
    )

    _send(client, hr_headers, application, ["10:30"])

    db_session.refresh(instance)
    assert "schedule" not in instance.payload
    assert "schedule_confirmation" not in instance.payload


# --- the round's length, saved on the job -----------------------------------


def test_interview_lengths_are_saved_with_the_workflow(client, db_session, hr_admin, make_job):
    job = make_job(WORKFLOW, title="Lengths Job")
    headers = auth_headers(client, hr_admin.email)

    # nothing saved yet: the defaults
    assert client.get(f"/hr/requisitions/{job.id}", headers=headers).json()["interview_durations"] == {
        "interview_round_1": 45
    }

    resp = client.patch(
        f"/hr/requisitions/{job.id}/workflow",
        headers=headers,
        json={"stages": WORKFLOW, "interview_durations": {"interview_round_1": 60}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["interview_durations"] == {"interview_round_1": 60}

    for bad in ({"interview_round_1": 50}, {"examination": 45}):
        resp = client.patch(
            f"/hr/requisitions/{job.id}/workflow",
            headers=headers,
            json={"stages": WORKFLOW, "interview_durations": bad},
        )
        assert resp.status_code == 422, bad


def test_deleting_a_job_takes_the_evaluators_ranges_with_it(
    client, db_session, evaluator, hr_admin, make_job, make_application
):
    job = _job(make_job, db_session, evaluator)
    application = make_application(job)
    instance = _on_interview(db_session, application, evaluator)
    _save_times(client, auth_headers(client, evaluator.email), instance, [(DAY, "09:00", "10:00")])
    application.status = ApplicationStatus.rejected
    db_session.flush()
    instance_id = instance.id

    resp = client.delete(f"/hr/requisitions/{job.id}", headers=auth_headers(client, hr_admin.email))

    assert resp.status_code == 204, resp.text
    assert db_session.scalars(
        select(InterviewAvailability).where(InterviewAvailability.stage_instance_id == instance_id)
    ).all() == []
    assert db_session.scalars(
        select(CandidateApplication).where(CandidateApplication.requisition_id == job.id)
    ).all() == []
