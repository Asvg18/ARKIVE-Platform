"""Black-box tests for POST /evaluator/interviews/{id}/evaluate -- the
Applicant Preliminary Interview Evaluation Form (HRD-F-APIEF) scorecard.
No prior coverage existed for this endpoint.
"""

import pytest

from app.domain.scorecard import SCORECARD_ITEM_CODES
from app.models.agent_run import AgentRun
from app.models.requisition_evaluator import RequisitionEvaluator
from tests.conftest import MOCK_RUBRIC_SCORE, auth_headers, give_confirmed_time

WORKFLOW_WITH_INTERVIEW = ["document_upload", "skill_matching", "interview_round_1", "final_decision"]


def _all_items(rating: int | None) -> dict[str, int | None]:
    return {code: rating for code in SCORECARD_ITEM_CODES}


def _advance_to(client, application, target_stage, headers, workflow):
    """Fast-forwards to `target_stage` for setup, acknowledging that the
    stages walked past have recorded nothing.

    Not boilerplate -- these tests are about what happens *at* the
    target stage, so the rounds before it are deliberately hollow, and
    the sufficiency gate is right to stop them. acknowledged_incomplete
    is the same escape hatch HR uses; the stages land as `skipped`
    rather than pretending to be complete."""
    for stage in workflow[workflow.index(application.current_stage.value) + 1 : workflow.index(target_stage) + 1]:
        resp = client.post(
            f"/applications/{application.id}/transition",
            json={
                "target_stage": stage,
                "acknowledged_incomplete": True,
                "reason": "Test setup: fast-forwarding to the stage under test.",
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text


def _assign_evaluator(client, db_session, job, application, evaluator_user, headers, stage_type="interview_round_1"):
    db_session.add(RequisitionEvaluator(requisition_id=job.id, evaluator_id=evaluator_user.id))
    db_session.flush()
    resp = client.post(
        f"/hr/applications/{application.id}/interview-assignment",
        json={"stage_type": stage_type, "evaluator_id": evaluator_user.id},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


def _stage_instance_id(client, headers, application_id: int) -> int:
    resp = client.get("/evaluator/interviews", headers=headers)
    assert resp.status_code == 200, resp.text
    return next(i["stage_instance_id"] for i in resp.json() if i["application_id"] == application_id)


def _setup(db_session, make_job, make_application, client, hr_admin, evaluator, *, confirmed_time=True):
    job = make_job(WORKFLOW_WITH_INTERVIEW)
    application = make_application(job)
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    # advance to interview_round_1 so it's in_progress and evaluable --
    # the queue lists assigned rounds whatever their status, but the
    # evaluate endpoint still requires the candidate to have reached the
    # round, so these tests must actually get there first
    _advance_to(client, application, "interview_round_1", hr_headers, WORKFLOW_WITH_INTERVIEW)
    _assign_evaluator(client, db_session, job, application, evaluator, hr_headers)
    eval_headers = auth_headers(client, "evaluator-test@arkivetesting.com")
    stage_instance_id = _stage_instance_id(client, eval_headers, application.id)
    # the form opens once the applicant has confirmed a time (step 19c)
    if confirmed_time:
        give_confirmed_time(db_session, stage_instance_id)
    return application, eval_headers, stage_instance_id


def test_full_valid_submission(client, db_session, make_job, make_application, hr_admin, evaluator):
    _, headers, stage_instance_id = _setup(db_session, make_job, make_application, client, hr_admin, evaluator)

    resp = client.post(
        f"/evaluator/interviews/{stage_instance_id}/evaluate",
        json={"item_ratings": _all_items(4), "remarks": "Solid candidate overall.", "recommendation": "recommended"},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    evaluation = resp.json()["evaluation"]
    assert evaluation["computed_score"] == 4.0
    assert evaluation["tier"] == "qualified"
    assert evaluation["remarks"] == "Solid candidate overall."
    assert evaluation["item_ratings"] == _all_items(4)
    assert evaluation["rubric_coverage_score"] == MOCK_RUBRIC_SCORE


def test_single_na_item_rejected(client, db_session, make_job, make_application, hr_admin, evaluator):
    """N/A was removed from the form (panel revisions, 15 Oct 2026):
    every item must carry a 1-5 rating."""
    _, headers, stage_instance_id = _setup(db_session, make_job, make_application, client, hr_admin, evaluator)

    ratings = _all_items(4)
    ratings["A1"] = None

    resp = client.post(
        f"/evaluator/interviews/{stage_instance_id}/evaluate",
        json={"item_ratings": ratings, "remarks": "One item left as N/A.", "recommendation": "recommended"},
        headers=headers,
    )

    assert resp.status_code == 422


def test_all_na_rejected(client, db_session, make_job, make_application, hr_admin, evaluator):
    _, headers, stage_instance_id = _setup(db_session, make_job, make_application, client, hr_admin, evaluator)

    resp = client.post(
        f"/evaluator/interviews/{stage_instance_id}/evaluate",
        json={"item_ratings": _all_items(None), "remarks": "Nothing applicable.", "recommendation": "recommended"},
        headers=headers,
    )

    assert resp.status_code == 422


def test_incomplete_item_codes_rejected(client, db_session, make_job, make_application, hr_admin, evaluator):
    _, headers, stage_instance_id = _setup(db_session, make_job, make_application, client, hr_admin, evaluator)

    ratings = _all_items(3)
    del ratings[SCORECARD_ITEM_CODES[0]]

    resp = client.post(
        f"/evaluator/interviews/{stage_instance_id}/evaluate",
        json={"item_ratings": ratings, "remarks": "Missing one item.", "recommendation": "recommended"},
        headers=headers,
    )

    assert resp.status_code == 422


@pytest.mark.parametrize(
    "ratings_builder,expected_tier",
    [
        (lambda: _all_items(5), "highly_qualified"),
        (lambda: _all_items(3), "qualified"),
        (
            lambda: {**_all_items(3), SCORECARD_ITEM_CODES[0]: 2},
            "not_qualified",
        ),
        (lambda: _all_items(1), "not_qualified"),
    ],
)
def test_tier_boundaries(
    client, db_session, make_job, make_application, hr_admin, evaluator, ratings_builder, expected_tier
):
    _, headers, stage_instance_id = _setup(db_session, make_job, make_application, client, hr_admin, evaluator)

    resp = client.post(
        f"/evaluator/interviews/{stage_instance_id}/evaluate",
        json={"item_ratings": ratings_builder(), "remarks": "Boundary check.", "recommendation": "recommended"},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["evaluation"]["tier"] == expected_tier


def test_resubmit_after_lock_returns_409(client, db_session, make_job, make_application, hr_admin, evaluator):
    _, headers, stage_instance_id = _setup(db_session, make_job, make_application, client, hr_admin, evaluator)

    first = client.post(
        f"/evaluator/interviews/{stage_instance_id}/evaluate",
        json={"item_ratings": _all_items(4), "remarks": "First submission.", "recommendation": "recommended"},
        headers=headers,
    )
    assert first.status_code == 200, first.text

    second = client.post(
        f"/evaluator/interviews/{stage_instance_id}/evaluate",
        json={"item_ratings": _all_items(2), "remarks": "Trying again.", "recommendation": "recommended"},
        headers=headers,
    )
    assert second.status_code == 409


def test_queue_lists_assigned_upcoming_interview(
    client, db_session, make_job, make_application, hr_admin, evaluator
):
    """The queue must show an interview the evaluator is assigned to even
    while the candidate has not reached it yet (`pending`). This is the
    bug that started this: HR assigns the panel up front and each
    assignment fires a notification, but the queue used to exclude
    `pending`, so the evaluator was told about interviews that never
    appeared in their list."""
    job = make_job(WORKFLOW_WITH_INTERVIEW)
    application = make_application(job)  # sits on document_upload; the round is pending
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    _assign_evaluator(client, db_session, job, application, evaluator, hr_headers)

    eval_headers = auth_headers(client, "evaluator-test@arkivetesting.com")
    resp = client.get("/evaluator/interviews", headers=eval_headers)
    assert resp.status_code == 200, resp.text
    row = next((i for i in resp.json() if i["application_id"] == application.id), None)
    assert row is not None, "an assigned but not-yet-reached interview should still be in the queue"
    assert row["status"] == "pending"
    assert row["already_evaluated"] is False


def test_evaluate_pending_interview_is_refused(
    client, db_session, make_job, make_application, hr_admin, evaluator
):
    """The other half of the queue fix: listing an upcoming round must not
    make it evaluable. The candidate has not reached it, so there is
    nothing to record, and the assignment notification links straight to
    this endpoint — so the guard has to live on the server, not only in
    the UI that hides the form."""
    job = make_job(WORKFLOW_WITH_INTERVIEW)
    application = make_application(job)
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    _assign_evaluator(client, db_session, job, application, evaluator, hr_headers)

    eval_headers = auth_headers(client, "evaluator-test@arkivetesting.com")
    stage_instance_id = _stage_instance_id(client, eval_headers, application.id)
    resp = client.post(
        f"/evaluator/interviews/{stage_instance_id}/evaluate",
        json={"item_ratings": _all_items(4), "remarks": "Too early.", "recommendation": "recommended"},
        headers=eval_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "hasn't reached" in resp.json()["detail"]


def test_agent_run_logged(client, db_session, make_job, make_application, hr_admin, evaluator):
    application, headers, stage_instance_id = _setup(
        db_session, make_job, make_application, client, hr_admin, evaluator
    )

    resp = client.post(
        f"/evaluator/interviews/{stage_instance_id}/evaluate",
        json={"item_ratings": _all_items(4), "remarks": "For the audit trail.", "recommendation": "recommended"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    db_session.flush()
    run = (
        db_session.query(AgentRun)
        .filter(
            AgentRun.application_id == application.id,
            AgentRun.agent_name == "evaluator_scorecard_agent",
        )
        .one()
    )
    assert run.triggered_by_stage == "interview_round_1"
    assert run.output["computed_score"] == 4.0
    assert run.output["tier"] == "qualified"

    synthesis_run = (
        db_session.query(AgentRun)
        .filter(
            AgentRun.application_id == application.id,
            AgentRun.agent_name == "interview_synthesis_agent",
        )
        .one()
    )
    assert synthesis_run.triggered_by_stage == "interview_round_1"
    assert synthesis_run.output["rubric_coverage_score"] == MOCK_RUBRIC_SCORE


def test_evaluator_consensus_score_on_profile(
    client, db_session, make_job, make_application, hr_admin, evaluator, make_user
):
    workflow = ["document_upload", "skill_matching", "interview_round_1", "interview_round_2", "final_decision"]
    job = make_job(workflow)
    application = make_application(job)
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    second_evaluator = make_user("evaluator2-test@arkivetesting.com", evaluator.role)
    db_session.add(RequisitionEvaluator(requisition_id=job.id, evaluator_id=evaluator.id))
    db_session.add(RequisitionEvaluator(requisition_id=job.id, evaluator_id=second_evaluator.id))
    db_session.flush()

    _advance_to(client, application, "interview_round_2", hr_headers, workflow)

    resp = client.post(
        f"/hr/applications/{application.id}/interview-assignment",
        json={"stage_type": "interview_round_1", "evaluator_id": evaluator.id},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        f"/hr/applications/{application.id}/interview-assignment",
        json={"stage_type": "interview_round_2", "evaluator_id": second_evaluator.id},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text

    profile = client.get(f"/hr/applications/{application.id}/profile", headers=hr_headers).json()
    assert profile["evaluator_consensus_score"] is None

    eval1_headers = auth_headers(client, "evaluator-test@arkivetesting.com")
    stage1_id = _stage_instance_id(client, eval1_headers, application.id)
    give_confirmed_time(db_session, stage1_id)
    resp = client.post(
        f"/evaluator/interviews/{stage1_id}/evaluate",
        json={"item_ratings": _all_items(5), "remarks": "Round 1.", "recommendation": "recommended"},
        headers=eval1_headers,
    )
    assert resp.status_code == 200, resp.text

    eval2_headers = auth_headers(client, "evaluator2-test@arkivetesting.com")
    stage2_id = _stage_instance_id(client, eval2_headers, application.id)
    give_confirmed_time(db_session, stage2_id)
    resp = client.post(
        f"/evaluator/interviews/{stage2_id}/evaluate",
        json={"item_ratings": _all_items(3), "remarks": "Round 2.", "recommendation": "recommended"},
        headers=eval2_headers,
    )
    assert resp.status_code == 200, resp.text

    profile = client.get(f"/hr/applications/{application.id}/profile", headers=hr_headers).json()
    assert profile["evaluator_consensus_score"] == 4.0
    # Only 2 of the 3 fixed roles are present in this job's workflow, so
    # this falls back to the equal-weighted mean (unchanged from before
    # the 30/30/40 weighting was added) — both rounds get the same mocked
    # rubric_coverage_score, so the mean is that same value.
    assert profile["interview_rubric_score"] == MOCK_RUBRIC_SCORE


def test_hr_profile_survives_legacy_single_rating_evaluation_shape(
    client, db_session, make_job, make_application, hr_admin, evaluator
):
    """Some interview_* StageInstance.payload["evaluation"] rows in the
    current dev DB predate the HRD-F-APIEF scorecard redesign — an
    "earlier single-rating shape" (only ai_summary/notes/rating/
    recommendation/submitted_by/submitted_at, no item_ratings/
    computed_score/tier/remarks/rubric_coverage_score at all). Confirmed
    against real seeded demo data (application ids 2, 3, 213). Guards
    against the HR Candidate Profile endpoint failing with a 500
    (KeyError: 'item_ratings') on them."""
    from app.models.stage_instance import StageInstance

    application, headers, stage_instance_id = _setup(db_session, make_job, make_application, client, hr_admin, evaluator)
    instance = db_session.get(StageInstance, stage_instance_id)
    instance.payload = {
        **(instance.payload or {}),
        "evaluation": {
            "ai_summary": "Old-format AI summary.",
            "notes": "Came across well in person.",
            "rating": 4,
            "recommendation": "advance",
            "submitted_by": evaluator.id,
            "submitted_at": "2025-01-01T00:00:00",
        },
    }
    db_session.flush()

    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    profile = client.get(f"/hr/applications/{application.id}/profile", headers=hr_headers)

    assert profile.status_code == 200, profile.text
    round_data = profile.json()["interview_ratings"]["interview_round_1"]
    assert round_data["ai_summary"] == "Old-format AI summary."
    assert round_data["submitted_at"] == "2025-01-01T00:00:00"
    assert round_data["item_ratings"] is None
    assert round_data["computed_score"] is None
    assert round_data["tier"] is None
    assert round_data["remarks"] is None
    assert round_data["rubric_coverage_score"] is None


# ---------------------------------------------------------------------------
# resolve_reschedule_request -- no prior coverage of this endpoint, or of
# request_reschedule (app/api/evaluator.py) that feeds it.
# ---------------------------------------------------------------------------


def _request_reschedule(client, eval_headers, stage_instance_id: int) -> int:
    resp = client.post(
        f"/evaluator/interviews/{stage_instance_id}/reschedule-request",
        json={"proposed_date": "2030-09-10", "proposed_time": "14:00", "reason": "Conflict with another panel."},
        headers=eval_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["stage_instance_id"]


def _pending_reschedule_id(client, hr_headers, application_id: int) -> int:
    profile = client.get(f"/hr/applications/{application_id}/profile", headers=hr_headers).json()
    return profile["interview_ratings"]["interview_round_1"]["reschedule_request"]["id"]


def test_resolve_reschedule_request_approve_writes_schedule_and_notifies(
    client, db_session, make_job, make_application, hr_admin, evaluator
):
    application, eval_headers, stage_instance_id = _setup(
        db_session, make_job, make_application, client, hr_admin, evaluator, confirmed_time=False
    )
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    _request_reschedule(client, eval_headers, stage_instance_id)
    request_id = _pending_reschedule_id(client, hr_headers, application.id)

    resp = client.post(
        f"/hr/applications/{application.id}/reschedule-requests/{request_id}/resolve",
        json={"decision": "approve", "date": "2030-09-10", "time": "14:00"},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text
    round_data = resp.json()["interview_ratings"]["interview_round_1"]
    # Resolved requests never surface as pending again — resolving the
    # returned CandidateProfile.reschedule_request back to None is how
    # resolve_reschedule_request's own query (status == pending) proves it
    # actually flipped the row's status, not just written the schedule.
    assert round_data["reschedule_request"] is None
    assert round_data["schedule"] == {"date": "2030-09-10", "time": "14:00"}

    # Two unread notifications by now: the interview-assignment one from
    # _setup's _assign_evaluator, plus this resolution — find the latter
    # by content rather than assuming list order/position.
    notifications = client.get("/notifications", headers=eval_headers).json()
    assert notifications["unread_count"] == 2
    resolution_message = next(i["message"] for i in notifications["items"] if "approved" in i["message"])
    assert "2030-09-10" in resolution_message


def test_resolve_reschedule_request_deny_leaves_schedule_untouched(
    client, db_session, make_job, make_application, hr_admin, evaluator
):
    application, eval_headers, stage_instance_id = _setup(
        db_session, make_job, make_application, client, hr_admin, evaluator, confirmed_time=False
    )
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    _request_reschedule(client, eval_headers, stage_instance_id)
    request_id = _pending_reschedule_id(client, hr_headers, application.id)

    resp = client.post(
        f"/hr/applications/{application.id}/reschedule-requests/{request_id}/resolve",
        json={"decision": "deny"},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text
    round_data = resp.json()["interview_ratings"]["interview_round_1"]
    assert round_data["reschedule_request"] is None
    # No schedule existed before the (denied) request, and denying one
    # must never invent one.
    assert round_data["schedule"] is None

    notifications = client.get("/notifications", headers=eval_headers).json()
    assert any("denied" in i["message"] for i in notifications["items"])


def test_resolve_reschedule_request_already_resolved_returns_409(
    client, db_session, make_job, make_application, hr_admin, evaluator
):
    application, eval_headers, stage_instance_id = _setup(db_session, make_job, make_application, client, hr_admin, evaluator)
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    _request_reschedule(client, eval_headers, stage_instance_id)
    request_id = _pending_reschedule_id(client, hr_headers, application.id)

    resp = client.post(
        f"/hr/applications/{application.id}/reschedule-requests/{request_id}/resolve",
        json={"decision": "deny"},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text

    resp = client.post(
        f"/hr/applications/{application.id}/reschedule-requests/{request_id}/resolve",
        json={"decision": "deny"},
        headers=hr_headers,
    )
    assert resp.status_code == 409, resp.text


# ---------------------------------------------------------------------------
# Evaluator-account CRUD -- no prior coverage of list_evaluators/
# add-to-pool. Account *creation* moved to app.api.invites -- GET /hr/
# evaluators stays here since WorkflowBuilderPage's evaluator-pool
# picker still depends on it, unrelated to how the account was created.
# ---------------------------------------------------------------------------


def test_list_evaluator_accounts(client, hr_admin, evaluator):
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.get("/hr/evaluators", headers=headers)

    assert resp.status_code == 200, resp.text
    assert any(e["email"] == evaluator.email for e in resp.json())


def test_add_evaluator_to_requisition_pool(client, hr_admin, evaluator, make_job):
    job = make_job(WORKFLOW_WITH_INTERVIEW)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        f"/hr/requisitions/{job.id}/evaluators",
        json={"evaluator_id": evaluator.id},
        headers=headers,
    )

    assert resp.status_code == 201, resp.text

    pool = client.get(f"/hr/requisitions/{job.id}/evaluators", headers=headers)
    assert pool.status_code == 200, pool.text
    assert any(e["evaluator_id"] == evaluator.id for e in pool.json())


# ---------------------------------------------------------------------------
# The evaluator's own overall recommendation — the "GENERAL EVALUATION AND
# RECOMMENDATION" box on the paper form, which the system previously only
# ever derived from the ratings rather than letting the evaluator answer.
# ---------------------------------------------------------------------------


def test_recommendation_is_required(client, db_session, make_job, make_application, hr_admin, evaluator):
    """On the paper form this box is not optional — an unchecked General
    Evaluation section is an incomplete submission."""
    _, eval_headers, stage_instance_id = _setup(
        db_session, make_job, make_application, client, hr_admin, evaluator
    )
    resp = client.post(
        f"/evaluator/interviews/{stage_instance_id}/evaluate",
        json={"item_ratings": _all_items(4), "remarks": "No recommendation given."},
        headers=eval_headers,
    )
    assert resp.status_code == 422, resp.text


def test_recommendation_rejects_a_value_outside_the_three_choices(
    client, db_session, make_job, make_application, hr_admin, evaluator
):
    _, eval_headers, stage_instance_id = _setup(
        db_session, make_job, make_application, client, hr_admin, evaluator
    )
    resp = client.post(
        f"/evaluator/interviews/{stage_instance_id}/evaluate",
        json={"item_ratings": _all_items(4), "remarks": "Maybe.", "recommendation": "maybe"},
        headers=eval_headers,
    )
    assert resp.status_code == 422, resp.text


def test_recommendation_is_stored_and_read_back_independently_of_the_tier(
    client, db_session, make_job, make_application, hr_admin, evaluator
):
    """The point of the field: a low recommendation on solid ratings is a
    real thing an interviewer can conclude, and the record has to keep
    both rather than reconciling them. Ratings of 4 band as `qualified`;
    the evaluator says do not advance."""
    _, eval_headers, stage_instance_id = _setup(
        db_session, make_job, make_application, client, hr_admin, evaluator
    )
    resp = client.post(
        f"/evaluator/interviews/{stage_instance_id}/evaluate",
        json={
            "item_ratings": _all_items(4),
            "remarks": "Competent on paper but would not thrive in this particular team.",
            "recommendation": "not_recommended",
        },
        headers=eval_headers,
    )
    assert resp.status_code == 200, resp.text

    evaluation = resp.json()["evaluation"]
    assert evaluation["tier"] == "qualified"
    assert evaluation["recommendation"] == "not_recommended"


def test_hr_sees_the_recommendation_on_the_candidate_profile(
    client, db_session, make_job, make_application, hr_admin, evaluator
):
    application, eval_headers, stage_instance_id = _setup(
        db_session, make_job, make_application, client, hr_admin, evaluator
    )
    application_id = application.id
    client.post(
        f"/evaluator/interviews/{stage_instance_id}/evaluate",
        json={
            "item_ratings": _all_items(5),
            "remarks": "Outstanding across every category; would hire immediately.",
            "recommendation": "highly_recommended",
        },
        headers=eval_headers,
    )
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    profile = client.get(f"/hr/applications/{application_id}/profile", headers=hr_headers).json()
    entry = next(r for r in profile["interview_ratings"].values() if r["submitted_at"])
    assert entry["recommendation"] == "highly_recommended"


def test_an_evaluation_predating_the_field_reads_as_none_rather_than_guessing(
    client, db_session, make_job, make_application, hr_admin, evaluator
):
    """Every evaluation already in the database was submitted before this
    field existed. It must surface as absent, never back-filled from the
    tier — inferring one would put words in a real evaluator's mouth."""
    from app.models.stage_instance import StageInstance

    application, eval_headers, stage_instance_id = _setup(
        db_session, make_job, make_application, client, hr_admin, evaluator
    )
    instance = db_session.get(StageInstance, stage_instance_id)
    instance.payload = {
        **(instance.payload or {}),
        "evaluation": {
            "item_ratings": _all_items(4),
            "computed_score": 4.0,
            "tier": "qualified",
            "remarks": "Submitted before the recommendation field existed.",
            "ai_summary": "",
            "rubric_coverage_score": 50.0,
            "submitted_by": evaluator.id,
            "submitted_at": "2026-08-01T00:00:00+00:00",
        },
    }
    db_session.commit()

    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    application_id = application.id
    profile = client.get(f"/hr/applications/{application_id}/profile", headers=hr_headers).json()
    entry = next(r for r in profile["interview_ratings"].values() if r["submitted_at"])
    assert entry["tier"] == "qualified"
    assert entry["recommendation"] is None
