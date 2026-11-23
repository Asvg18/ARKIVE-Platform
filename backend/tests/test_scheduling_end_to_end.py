"""Step 19 end to end (panel revision list, 15 Oct 2026), through the API
the screens use: HR adds exam sessions, the applicant books one, HR
records the score with the date taken; then the evaluator gives free
times, HR sends them, the applicant picks one, and only then does the
evaluator's scorecard go through."""

from sqlalchemy import select

from app.models.enums import StageStatus, StageType
from app.models.requisition_evaluator import RequisitionEvaluator
from app.models.stage_instance import StageInstance
from tests.conftest import auth_headers
from tests.test_evaluator import _all_items

WORKFLOW = ["document_upload", "examination", "interview_round_1", "final_decision"]


def test_exam_then_interview_from_sessions_to_scorecard(
    client, db_session, hr_admin, applicant, evaluator, make_job, make_application
):
    job = make_job(WORKFLOW, title="End To End")
    db_session.add(RequisitionEvaluator(requisition_id=job.id, evaluator_id=evaluator.id))
    application = make_application(job)
    application.current_stage = StageType.examination
    exam = db_session.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id, StageInstance.stage_type == StageType.examination
        )
    )
    exam.status = StageStatus.in_progress
    db_session.flush()
    hr = auth_headers(client, hr_admin.email)
    me = auth_headers(client, applicant.email)
    ev = auth_headers(client, evaluator.email)

    # HR adds sessions in one go
    resp = client.post(
        f"/hr/requisitions/{job.id}/exam-slots/batch",
        headers=hr,
        json={
            "stage_type": "examination",
            "dates": ["2030-03-01", "2030-03-02"],
            "windows": [{"start": "09:00", "end": "11:30"}],
            "seats": 10,
            "location": "Room 204",
        },
    )
    assert resp.status_code == 201, resp.text

    # the applicant books one inside the Examination stage
    sessions = client.get(f"/applicant/applications/{application.id}", headers=me).json()["exam_sessions"]
    assert [s["date"] for s in sessions] == ["2030-03-01", "2030-03-02"]
    resp = client.post(
        f"/applicant/applications/{application.id}/exam-booking",
        headers=me,
        json={"stage_type": "examination", "exam_slot_id": sessions[0]["id"]},
    )
    assert resp.status_code == 200, resp.text

    # HR records the score; the date taken defaults to the booked session's
    resp = client.patch(
        f"/hr/applications/{application.id}/examination-result",
        headers=hr,
        json={"stage_type": "examination", "score": 85},
    )
    assert resp.json()["examinations"]["examination"]["taken_on"] == "2030-03-01"

    # on to the interview, with an evaluator on it
    resp = client.post(
        f"/applications/{application.id}/transition",
        headers=hr,
        json={"target_stage": "interview_round_1", "acknowledged_incomplete": True, "reason": "Test: exam done."},
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        f"/hr/applications/{application.id}/interview-assignment",
        headers=hr,
        json={"stage_type": "interview_round_1", "evaluator_id": evaluator.id},
    )
    assert resp.status_code == 200, resp.text
    round_id = next(
        i["stage_instance_id"]
        for i in client.get("/evaluator/interviews", headers=ev).json()
        if i["application_id"] == application.id
    )
    scorecard = {"item_ratings": _all_items(4), "remarks": "Good.", "recommendation": "recommended"}

    # the evaluator gives free times; the form is still locked
    resp = client.put(
        f"/evaluator/interviews/{round_id}/availability",
        headers=ev,
        json={"windows": [{"date": "2030-03-05", "start": "09:00", "end": "10:30"}]},
    )
    assert resp.status_code == 200, resp.text
    assert client.post(f"/evaluator/interviews/{round_id}/evaluate", headers=ev, json=scorecard).status_code == 409

    # HR sends the cut slots; the applicant picks one
    choices = client.get(f"/hr/applications/{application.id}/profile", headers=hr).json()["interview_ratings"][
        "interview_round_1"
    ]["slot_choices"]
    assert [c["time"] for c in choices] == ["09:00", "09:45"]
    resp = client.post(
        f"/hr/applications/{application.id}/interview-slots",
        headers=hr,
        json={
            "stage_type": "interview_round_1",
            "slots": [{"date": c["date"], "time": c["time"]} for c in choices],
            "mode": "online",
            "meeting_link": "https://meet.example.com/abc",
        },
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        f"/applicant/applications/{application.id}/interview-slot",
        headers=me,
        json={"stage_type": "interview_round_1", "date": "2030-03-05", "time": "09:45"},
    )
    assert resp.status_code == 200, resp.text

    # picked = confirmed, so the form opens
    detail = client.get(f"/evaluator/interviews/{round_id}", headers=ev).json()
    assert detail["schedule_confirmed"] is True
    assert detail["schedule"]["meeting_link"] == "https://meet.example.com/abc"
    resp = client.post(f"/evaluator/interviews/{round_id}/evaluate", headers=ev, json=scorecard)
    assert resp.status_code == 200, resp.text
