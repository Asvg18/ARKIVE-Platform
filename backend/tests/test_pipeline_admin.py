"""Tests for the general HR pipeline-admin endpoints: GET /hr/dashboard/
summary, PATCH /hr/requisitions/{id}/workflow, and GET /hr/applications
(the Pipeline page listing). None of these are exercised end-to-end by
any other test file.
"""

import pytest

from app.models.enums import ApplicationStatus
from tests.conftest import auth_headers

WORKFLOW = ["document_upload", "skill_matching", "final_decision"]


def test_dashboard_summary_counts_are_real(client, hr_admin, make_job, make_application):
    job = make_job(WORKFLOW, title="Dashboard Test Job")
    make_application(job)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.get("/hr/dashboard/summary", headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["open_requisitions"] >= 1
    assert body["active_candidates"] >= 1
    # tests run against the real dev DB inside a rolled-back transaction
    # -- real seeded demo data is visible alongside this test's own
    # rows, so avg_time_to_hire_days can't be asserted None here, just
    # confirm the field's shape is sane
    assert body["avg_time_to_hire_days"] is None or body["avg_time_to_hire_days"] >= 0
    assert any(r["title"] == "Dashboard Test Job" for r in body["requisitions"])


def test_update_requisition_workflow_success(client, hr_admin, make_job):
    job = make_job(WORKFLOW)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch(
        f"/hr/requisitions/{job.id}/workflow",
        json={"stages": ["document_upload", "skill_matching", "shortlisting", "examination", "interview_round_1", "final_decision", "onboarding"]},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["workflow_definition"] == [
        "document_upload", "skill_matching", "shortlisting", "examination", "interview_round_1", "final_decision", "onboarding"
    ]


def test_workflow_save_rejects_a_nonsensical_order(client, hr_admin, make_job):
    """The rules from app.domain.workflow_rules are enforced on save. A
    sequence with Onboarding before the Final Decision is refused, and the
    426 error carries a readable reason (rendered by client.ts, W2)."""
    job = make_job(WORKFLOW)  # a sensible starting workflow, no active candidates
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch(
        f"/hr/requisitions/{job.id}/workflow",
        json={"stages": ["document_upload", "skill_matching", "onboarding", "final_decision"]},
        headers=headers,
    )

    assert resp.status_code == 422, resp.text
    assert "Onboarding must be the last stage" in resp.json()["detail"]


def test_workflow_save_rejects_document_upload_not_first(client, hr_admin, make_job):
    job = make_job(WORKFLOW)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch(
        f"/hr/requisitions/{job.id}/workflow",
        json={"stages": ["skill_matching", "document_upload", "final_decision"]},
        headers=headers,
    )

    assert resp.status_code == 422, resp.text
    assert "Document Upload must be the first stage" in resp.json()["detail"]


def test_workflow_save_rejects_a_retired_check_stage(client, hr_admin, make_job):
    """Reference and background checks were retired on 30 Sep 2026.
    Still StageType values for stage_history's sake, so the schema lets
    them through -- the rules are what keep them out of a workflow."""
    job = make_job(WORKFLOW)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    for stage in ("reference_check", "background_check"):
        resp = client.patch(
            f"/hr/requisitions/{job.id}/workflow",
            json={"stages": ["document_upload", "skill_matching", stage, "final_decision"]},
            headers=headers,
        )

        assert resp.status_code == 422, resp.text
        assert "no longer part of ARKIVE" in resp.json()["detail"]


def test_workflow_save_allows_a_warning_only_workflow(client, hr_admin, make_job):
    """Omitting AI Pre-Screening is a warning, not an error — a legal, if
    probably-unintended, pipeline. The save must go through; the warning
    is the live checklist's job to surface, not the save's to refuse."""
    job = make_job(WORKFLOW)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch(
        f"/hr/requisitions/{job.id}/workflow",
        json={"stages": ["document_upload", "shortlisting", "interview_round_1", "final_decision", "onboarding"]},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text


def test_workflow_save_grandfathers_an_existing_bad_order_on_a_label_only_edit(
    client, hr_admin, make_job
):
    """A workflow authored before these rules existed keeps running, and a
    rename to such a job must not be held hostage to a sequence it did not
    touch — the validation runs only when the order actually changes. The
    job is created directly (make_job bypasses the endpoint), giving it an
    order the rules would now reject: Onboarding is not last."""
    bad_order = ["document_upload", "interview_round_1", "onboarding", "final_decision"]
    job = make_job(bad_order)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    # Same sequence, only a label changes → allowed despite the bad order.
    resp = client.patch(
        f"/hr/requisitions/{job.id}/workflow",
        json={"stages": bad_order, "interview_round_labels": {"interview_round_1": "Panel Interview"}},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["interview_round_labels"]["interview_round_1"] == "Panel Interview"

    # But actually changing the sequence to another bad order is now caught.
    resp = client.patch(
        f"/hr/requisitions/{job.id}/workflow",
        json={"stages": ["onboarding", "document_upload", "final_decision"]},
        headers=headers,
    )
    assert resp.status_code == 422, resp.text


def test_validate_workflow_endpoint_reports_errors_and_warnings(client, hr_admin):
    """The live checklist's source: same rules as the save, returned as a
    structured list rather than enforced, so the builder can show them as
    HR edits. This list has one of each severity — an exam after the final
    decision (error) and no AI Pre-Screening (warning)."""
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        "/hr/requisitions/validate-workflow",
        json={"stages": ["document_upload", "final_decision", "examination", "onboarding"]},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    issues = resp.json()["issues"]
    severities = {i["severity"] for i in issues}
    codes = {i["code"] for i in issues}
    assert "error" in severities and "warning" in severities
    assert "final_decision_after_evaluations" in codes  # the exam sits after the decision
    assert "no_skill_matching" in codes


def test_validate_workflow_endpoint_passes_a_clean_workflow(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    resp = client.post(
        "/hr/requisitions/validate-workflow",
        json={"stages": ["document_upload", "skill_matching", "shortlisting", "examination", "interview_round_1", "final_decision", "onboarding"]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["issues"] == []


def test_a_workflow_needs_an_interview(client, hr_admin):
    """23 Oct 2026: a workflow with no interview round can't be saved or published."""
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    stages = ["document_upload", "skill_matching", "shortlisting", "final_decision", "onboarding"]
    assert "interview_required" in _codes(client, headers, stages)
    assert "interview_required" not in _codes(client, headers, stages[:3] + ["interview_round_1"] + stages[3:])


def _codes(client, headers, stages):
    resp = client.post("/hr/requisitions/validate-workflow", json={"stages": stages}, headers=headers)
    assert resp.status_code == 200, resp.text
    return {i["code"] for i in resp.json()["issues"] if i["severity"] == "error"}


def test_shortlisting_cannot_be_removed(client, hr_admin):
    """Panel revision list, 15 Oct 2026: every workflow keeps Shortlisting."""
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    codes = _codes(client, headers, ["document_upload", "interview_round_1", "final_decision", "onboarding"])
    assert "shortlisting_required" in codes


def test_shortlisting_must_come_before_every_interview(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    codes = _codes(
        client, headers,
        ["document_upload", "interview_round_1", "shortlisting", "interview_round_2", "final_decision"],
    )
    assert "shortlisting_before_interviews" in codes


def test_an_exam_may_come_before_shortlisting(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    codes = _codes(
        client, headers,
        ["document_upload", "examination", "shortlisting", "interview_round_1", "final_decision", "onboarding"],
    )
    assert codes == set()


@pytest.mark.parametrize(
    ("missing", "code"),
    [
        ("document_upload", "document_upload_first"),
        ("shortlisting", "shortlisting_required"),
        ("final_decision", "final_decision_required"),
        ("onboarding", "onboarding_required"),
    ],
)
def test_the_required_stages_cannot_be_removed(client, hr_admin, missing, code):
    """Document Upload, Shortlisting, Final Decision and Onboarding are in
    every workflow (20 Oct 2026); the builder shows no remove button on
    them, and a list without one is refused."""
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    full = ["document_upload", "shortlisting", "interview_round_1", "final_decision", "onboarding"]
    codes = _codes(client, headers, [stage for stage in full if stage != missing])
    assert code in codes


def test_update_requisition_workflow_blocked_with_active_candidates(client, make_job, make_application, hr_admin):
    job = make_job(WORKFLOW)
    make_application(job)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch(
        f"/hr/requisitions/{job.id}/workflow",
        json={"stages": ["document_upload", "final_decision"]},
        headers=headers,
    )

    assert resp.status_code == 409, resp.text


def test_renaming_a_round_is_allowed_while_candidates_are_active(
    client, hr_admin, make_job, make_application
):
    """The lock is on the stage *sequence*, not on the page. Round and
    examination names are display-only, so a rename cannot move anyone's
    DFA position — and a job should not be uncorrectable for the whole
    time it has candidates in it."""
    stages = ["document_upload", "interview_round_1", "final_decision"]
    job = make_job(stages)
    make_application(job)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch(
        f"/hr/requisitions/{job.id}/workflow",
        json={"stages": stages, "interview_round_labels": {"interview_round_1": "Panel Interview"}},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["interview_round_labels"]["interview_round_1"] == "Panel Interview"
    assert resp.json()["workflow_definition"] == stages

    # ...while the same job still refuses an actual change of sequence.
    resp = client.patch(
        f"/hr/requisitions/{job.id}/workflow",
        json={"stages": ["document_upload", "final_decision"]},
        headers=headers,
    )
    assert resp.status_code == 409


def test_the_evaluator_pool_is_not_locked_by_active_candidates(
    client, hr_admin, evaluator, make_job, make_application
):
    """An evaluator's availability changes on its own timetable, not the
    pipeline's — someone resigning or going on leave mid-hiring is
    ordinary. Adding to the pool has never been gated and this pins that
    down; only *removing* an evaluator already assigned to an active
    candidate is refused, and that guard is tested in test_decision_support."""
    job = make_job(WORKFLOW)
    make_application(job)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        f"/hr/requisitions/{job.id}/evaluators",
        json={"evaluator_id": evaluator.id},
        headers=headers,
    )

    assert resp.status_code == 201, resp.text


def test_list_applications_returns_next_stage(client, hr_admin, make_job, make_application):
    job = make_job(WORKFLOW)
    application = make_application(job)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.get("/hr/applications", headers=headers)

    assert resp.status_code == 200, resp.text
    row = next(item for item in resp.json() if item["id"] == application.id)
    assert row["current_stage"] == "document_upload"
    assert row["next_stage"] == "skill_matching"
    assert row["status"] == "active"


def test_dashboard_rows_do_not_carry_the_delete_gating_counts(
    client, hr_admin, make_job, make_application, db_session
):
    """Deleting a job opening is offered on the Job Openings page and
    nowhere else, so the dashboard has no use for the two counts that
    gated it -- and each one cost a COUNT query per requisition on every
    load of the Command Center."""
    job = make_job(WORKFLOW, title="Dashboard Row Shape")
    make_application(job)
    db_session.flush()
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    rows = {r["id"]: r for r in client.get("/hr/dashboard/summary", headers=headers).json()["requisitions"]}

    assert rows[job.id]["active_candidate_count"] == 1
    assert "in_flight_candidate_count" not in rows[job.id]
    assert "application_count" not in rows[job.id]
