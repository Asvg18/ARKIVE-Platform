"""Tests for GET /hr/applications/{id}/pre-201-package -- the compiled,
read-only record bundle for a hired applicant. New coverage; the
endpoint didn't exist before."""

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


def test_pre_201_package_404_for_missing_application(client, hr_admin):
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.get("/hr/applications/999999/pre-201-package", headers=hr_headers)

    assert resp.status_code == 404


def test_pre_201_package_rejects_non_hired_application(client, make_job, make_application, hr_admin):
    job = make_job(WORKFLOW)
    application = make_application(job)
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.get(f"/hr/applications/{application.id}/pre-201-package", headers=hr_headers)

    assert resp.status_code == 409


def test_pre_201_package_compiles_full_record_once_hired(
    client, db_session, make_job, make_application, make_resume, hr_admin
):
    job = make_job(WORKFLOW)
    application = make_application(job)
    make_resume(application, skills=["Python", "SQL"])
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    _advance_to(client, application, "final_decision", hr_headers, WORKFLOW)

    # acknowledged_incomplete because this fixture deliberately skips the
    # skill-match and exam scores -- the hire gate would otherwise 409.
    # exercising the escape hatch is the point: the package must compile
    # from a knowingly incomplete record too, since that's what a real
    # one often is.
    resp = client.patch(
        f"/hr/applications/{application.id}/status",
        json={"status": "hired", "acknowledged_incomplete": True, "reason": "Seeded fixture — record intentionally partial."},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text

    resp = client.get(f"/hr/applications/{application.id}/pre-201-package", headers=hr_headers)

    assert resp.status_code == 200, resp.text
    package = resp.json()
    assert package["application_id"] == application.id
    assert package["job_title"] == job.title
    assert package["resume"]["skills"] == ["Python", "SQL"]
    assert "checks" not in package
    assert package["hired_at"] is not None
