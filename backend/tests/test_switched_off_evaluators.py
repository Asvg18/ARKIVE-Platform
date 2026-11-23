"""A switched-off evaluator can no longer sign in, so they must not be
offered for, added to, or given an interview -- and switching one off
should show HR which interviews they still owe.

Before 28 Sep 2026 the Workflow Builder's picker listed every evaluator
account ever made, switched off or not, and nothing said an interview
was now waiting on somebody who could never do it.
"""

from app.models.requisition_evaluator import RequisitionEvaluator
from tests.conftest import auth_headers

WORKFLOW = ["document_upload", "skill_matching", "interview_round_1", "final_decision"]


def _switch_off(client, hr_admin, user):
    resp = client.post(f"/hr/staff/{user.id}/deactivate", headers=auth_headers(client, hr_admin.email))
    assert resp.status_code == 200, resp.text


def _in_pool(db_session, job, user):
    db_session.add(RequisitionEvaluator(requisition_id=job.id, evaluator_id=user.id))
    db_session.flush()


def _assign(client, headers, application, evaluator_id):
    return client.post(
        f"/hr/applications/{application.id}/interview-assignment",
        json={"stage_type": "interview_round_1", "evaluator_id": evaluator_id},
        headers=headers,
    )


def test_the_picker_no_longer_offers_a_switched_off_evaluator(client, hr_admin, evaluator):
    headers = auth_headers(client, hr_admin.email)
    ids = lambda: {e["id"] for e in client.get("/hr/evaluators", headers=headers).json()}  # noqa: E731
    assert evaluator.id in ids()

    _switch_off(client, hr_admin, evaluator)

    assert evaluator.id not in ids()


def test_a_switched_off_evaluator_cannot_be_added_to_a_pool(client, hr_admin, evaluator, make_job):
    job = make_job(WORKFLOW)
    _switch_off(client, hr_admin, evaluator)

    resp = client.post(
        f"/hr/requisitions/{job.id}/evaluators",
        json={"evaluator_id": evaluator.id},
        headers=auth_headers(client, hr_admin.email),
    )
    assert resp.status_code == 422, resp.text


def test_the_pool_says_which_members_are_switched_off(client, hr_admin, evaluator, make_job, db_session):
    """They stay in the pool -- their history on the job stays -- and the
    Workflow Builder marks them."""
    job = make_job(WORKFLOW)
    _in_pool(db_session, job, evaluator)
    _switch_off(client, hr_admin, evaluator)

    pool = client.get(f"/hr/requisitions/{job.id}/evaluators", headers=auth_headers(client, hr_admin.email))
    [member] = pool.json()
    assert member["evaluator_id"] == evaluator.id
    assert member["is_active"] is False


def test_an_interview_cannot_be_given_to_a_switched_off_evaluator(
    client, hr_admin, evaluator, make_job, make_application, db_session
):
    job = make_job(WORKFLOW)
    application = make_application(job)
    _in_pool(db_session, job, evaluator)
    _switch_off(client, hr_admin, evaluator)

    resp = _assign(client, auth_headers(client, hr_admin.email), application, evaluator.id)
    assert resp.status_code == 422, resp.text


def test_an_interview_already_theirs_can_still_be_saved_or_taken_back(
    client, hr_admin, evaluator, make_job, make_application, db_session
):
    """Refusing these would trap HR: the round has to be movable off a
    person who has left."""
    job = make_job(WORKFLOW)
    application = make_application(job)
    _in_pool(db_session, job, evaluator)
    headers = auth_headers(client, hr_admin.email)
    assert _assign(client, headers, application, evaluator.id).status_code == 200
    _switch_off(client, hr_admin, evaluator)

    assert _assign(client, headers, application, evaluator.id).status_code == 200
    assert _assign(client, headers, application, None).status_code == 200


def test_switching_off_shows_the_interviews_still_waiting(
    client, hr_admin, evaluator, make_job, make_application, db_session
):
    job = make_job(WORKFLOW, title="Registrar")
    application = make_application(job)
    _in_pool(db_session, job, evaluator)
    headers = auth_headers(client, hr_admin.email)
    _assign(client, headers, application, evaluator.id)

    waiting = client.get(f"/hr/staff/{evaluator.id}/waiting-interviews", headers=headers)
    assert waiting.status_code == 200, waiting.text
    [row] = waiting.json()
    assert row["application_id"] == application.id
    assert row["job_title"] == "Registrar"
    assert row["candidate_name"]
    assert row["stage_label"]

    _assign(client, headers, application, None)
    assert client.get(f"/hr/staff/{evaluator.id}/waiting-interviews", headers=headers).json() == []


def test_an_hr_admin_never_has_interviews_waiting(client, hr_admin, plain_hr_admin):
    resp = client.get(
        f"/hr/staff/{plain_hr_admin.id}/waiting-interviews", headers=auth_headers(client, hr_admin.email)
    )
    assert resp.json() == []
