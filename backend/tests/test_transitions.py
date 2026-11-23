"""Black-box test cases for POST /applications/{id}/transition and
GET /hr/applications. Each test only asserts on observable behavior
(status codes, response bodies, DB state) -- none reach into the DFA
generator directly, since the point is to prove the endpoint behaves
correctly end-to-end, the same way a demo would.
"""

from app.models.stage_history import StageHistory

from tests.conftest import auth_headers

SIMPLE_WORKFLOW = ["document_upload", "skill_matching", "final_decision"]


def test_advance_to_correct_next_stage_succeeds(client, db_session, make_job, make_application, make_resume):
    job = make_job(SIMPLE_WORKFLOW)
    application = make_application(job)
    # A resume, because Document Upload will not advance without one
    # (app.domain.stage_requirements.TRANSITION_BLOCKING_KEYS).
    make_resume(application)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        f"/applications/{application.id}/transition",
        json={"target_stage": "skill_matching"},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["previous_stage"] == "document_upload"
    assert body["current_stage"] == "skill_matching"

    db_session.refresh(application)
    assert application.current_stage.value == "skill_matching"

    history = db_session.query(StageHistory).filter_by(application_id=application.id).all()
    assert len(history) == 1
    assert history[0].from_stage.value == "document_upload"
    assert history[0].to_stage.value == "skill_matching"


def test_non_adjacent_jump_rejected_with_no_state_change(client, db_session, make_job, make_application):
    job = make_job(SIMPLE_WORKFLOW)
    application = make_application(job)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        f"/applications/{application.id}/transition",
        json={"target_stage": "final_decision"},
        headers=headers,
    )

    assert resp.status_code == 422
    # The rejection is written in the stage names HR gave this job, not in
    # database keys — it is read by an HR admin on the pipeline board, at
    # the moment they drag a candidate somewhere the automaton forbids.
    detail = resp.json()["detail"]
    assert "Final Decision" in detail
    assert "Document Upload" in detail
    # It must also name the one move that *would* have been legal, which
    # is the whole point of a single-successor automaton.
    assert "Pre-Screening" in detail

    db_session.refresh(application)
    assert application.current_stage.value == "document_upload"
    assert db_session.query(StageHistory).filter_by(application_id=application.id).count() == 0


def test_advance_past_terminal_stage_rejected(client, db_session, make_job, make_application, make_resume):
    job = make_job(SIMPLE_WORKFLOW)
    application = make_application(job)
    # A resume, because Document Upload will not advance without one
    # (app.domain.stage_requirements.TRANSITION_BLOCKING_KEYS).
    make_resume(application)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    for target in SIMPLE_WORKFLOW[1:]:
        resp = client.post(
            f"/applications/{application.id}/transition",
            json={"target_stage": target},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

    # "document_upload" is a real stage in this job's workflow, just not
    # a valid one from the now-terminal "final_decision" — this is what
    # actually exercises the terminal-stage branch (a stage name that
    # isn't part of the workflow at all hits a different, earlier check).
    resp = client.post(
        f"/applications/{application.id}/transition",
        json={"target_stage": "document_upload"},
        headers=headers,
    )
    assert resp.status_code == 422
    assert "terminal" in resp.json()["detail"]


def test_evaluator_forbidden(client, evaluator, make_job, make_application):
    job = make_job(SIMPLE_WORKFLOW)
    application = make_application(job)
    headers = auth_headers(client, "evaluator-test@arkivetesting.com")

    resp = client.post(
        f"/applications/{application.id}/transition",
        json={"target_stage": "skill_matching"},
        headers=headers,
    )
    assert resp.status_code == 403


def test_applicant_forbidden(client, applicant, make_job, make_application):
    job = make_job(SIMPLE_WORKFLOW)
    application = make_application(job)
    headers = auth_headers(client, "applicant-test@arkivetesting.com")

    resp = client.post(
        f"/applications/{application.id}/transition",
        json={"target_stage": "skill_matching"},
        headers=headers,
    )
    assert resp.status_code == 403


def test_nonexistent_application_returns_404_not_403(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        "/applications/999999/transition",
        json={"target_stage": "skill_matching"},
        headers=headers,
    )
    assert resp.status_code == 404


def test_full_happy_path_walks_first_to_last_stage(client, db_session, make_job, make_application, make_resume):
    job = make_job(SIMPLE_WORKFLOW)
    application = make_application(job)
    # A resume, because Document Upload will not advance without one
    # (app.domain.stage_requirements.TRANSITION_BLOCKING_KEYS).
    make_resume(application)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    for target in SIMPLE_WORKFLOW[1:]:
        resp = client.post(
            f"/applications/{application.id}/transition",
            json={"target_stage": target},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

    db_session.refresh(application)
    assert application.current_stage.value == SIMPLE_WORKFLOW[-1]

    history = (
        db_session.query(StageHistory)
        .filter_by(application_id=application.id)
        .order_by(StageHistory.id)
        .all()
    )
    assert [h.to_stage.value for h in history] == SIMPLE_WORKFLOW[1:]


def test_hr_applications_list_includes_computed_next_stage(client, make_job, make_application):
    job = make_job(SIMPLE_WORKFLOW)
    application = make_application(job)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.get("/hr/applications", headers=headers)
    assert resp.status_code == 200, resp.text

    row = next(item for item in resp.json() if item["id"] == application.id)
    assert row["current_stage"] == "document_upload"
    assert row["next_stage"] == "skill_matching"
