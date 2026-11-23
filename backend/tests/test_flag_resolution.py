"""Tests for POST /hr/applications/{id}/resolve-flag -- HR's verdict on
a Skill Matching flag. Applications are flagged directly via db_session
rather than through a real low-score skill-matching run
(test_skill_matching.py covers what makes the agent flag something) --
this file is purely about resolve_flag's own branching once an
application is already flagged.
"""

from app.models.enums import ApplicationStatus, StageType
from app.models.stage_instance import StageInstance
from tests.conftest import auth_headers

WORKFLOW = ["document_upload", "skill_matching", "final_decision"]


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


def _flag_at_skill_matching(client, db_session, application, hr_headers):
    _advance_to(client, application, "skill_matching", hr_headers, WORKFLOW)
    instance = (
        db_session.query(StageInstance)
        .filter(StageInstance.application_id == application.id, StageInstance.stage_type == StageType.skill_matching)
        .one()
    )
    instance.payload = {"match_score": 42.0, "flagged": True}
    application.status = ApplicationStatus.flagged
    db_session.flush()


def test_resolve_flag_continue_advances_dfa_and_preserves_payload(
    client, db_session, make_job, make_application, hr_admin
):
    job = make_job(WORKFLOW)
    application = make_application(job)
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    _flag_at_skill_matching(client, db_session, application, hr_headers)

    resp = client.post(
        f"/hr/applications/{application.id}/resolve-flag",
        json={"decision": "continue"},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text
    profile = resp.json()
    assert profile["current_stage"] == "final_decision"
    assert profile["flagged"] is False
    # no current_stage_payload was passed to transition_application_stage,
    # so the flagged skill_matching analysis must survive the advance
    # untouched
    assert profile["match_score"] == 42.0


def test_resolve_flag_reject_closes_application_without_advancing(
    client, db_session, make_job, make_application, hr_admin
):
    job = make_job(WORKFLOW)
    application = make_application(job)
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    _flag_at_skill_matching(client, db_session, application, hr_headers)

    resp = client.post(
        f"/hr/applications/{application.id}/resolve-flag",
        json={"decision": "reject"},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text
    profile = resp.json()
    assert profile["status"] == "rejected"
    # Rejecting just closes the application — it never advances the DFA
    # the way "continue" does.
    assert profile["current_stage"] == "skill_matching"


def test_resolve_flag_on_non_flagged_application_returns_409(
    client, db_session, make_job, make_application, hr_admin
):
    job = make_job(WORKFLOW)
    application = make_application(job)
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        f"/hr/applications/{application.id}/resolve-flag",
        json={"decision": "continue"},
        headers=hr_headers,
    )
    assert resp.status_code == 409, resp.text
