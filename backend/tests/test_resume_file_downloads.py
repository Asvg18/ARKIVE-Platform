"""Tests for the two resume-file download endpoints: GET /hr/
applications/{id}/resume-file and GET /evaluator/applications/{id}/
resume-file. Both let their respective role open the candidate's real
uploaded PDF, not just the AI-extracted fields -- and the evaluator one
is scoped to only applications with an interview stage actually
assigned to that evaluator, never any application by raw id.
"""

import json
from pathlib import Path

from tests.conftest import auth_headers

WORKFLOW = ["document_upload", "skill_matching", "final_decision"]
WORKFLOW_WITH_INTERVIEW = ["document_upload", "skill_matching", "interview_round_1", "final_decision"]
_SAMPLE_RESUME_PDF = next((Path(__file__).parent.parent / "uploads" / "resumes").glob("*.pdf"))
_RESUME_DATA = {
    "full_name": "Ada Applicant",
    "email": "applicant-test@arkivetesting.com",
    "phone": "09171234567",
    "location": "Lucena City",
    "linkedin_url": "",
    "portfolio_url": "",
    "professional_summary": "QA-focused engineer.",
    "education": [],
    "experience": [],
    "skills": ["Testing"],
    "certifications": [],
}


def _upload_real_resume(client, applicant_headers, application_id: int) -> None:
    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        resp = client.post(
            f"/applicant/applications/{application_id}/document-upload",
            headers=applicant_headers,
            files={"resume_file": ("resume.pdf", f, "application/pdf")},
            data={"resume_data": json.dumps(_RESUME_DATA)},
        )
    assert resp.status_code == 200, resp.text


def test_hr_downloads_candidate_resume_file(client, applicant, hr_admin, make_job):
    job = make_job(WORKFLOW)
    applicant_headers = auth_headers(client, applicant.email)
    application_id = client.post("/applications", json={"requisition_id": job.id}, headers=applicant_headers).json()["id"]
    _upload_real_resume(client, applicant_headers, application_id)

    hr_headers = auth_headers(client, hr_admin.email)
    resp = client.get(f"/hr/applications/{application_id}/resume-file", headers=hr_headers)

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"


def test_hr_resume_file_404_when_not_uploaded(client, applicant, hr_admin, make_job):
    job = make_job(WORKFLOW)
    applicant_headers = auth_headers(client, applicant.email)
    application_id = client.post("/applications", json={"requisition_id": job.id}, headers=applicant_headers).json()["id"]

    hr_headers = auth_headers(client, hr_admin.email)
    resp = client.get(f"/hr/applications/{application_id}/resume-file", headers=hr_headers)

    assert resp.status_code == 404, resp.text


def test_evaluator_downloads_resume_file_for_assigned_interview(
    client, db_session, applicant, hr_admin, evaluator, make_job
):
    from app.models.requisition_evaluator import RequisitionEvaluator

    job = make_job(WORKFLOW_WITH_INTERVIEW)
    applicant_headers = auth_headers(client, applicant.email)
    application_id = client.post("/applications", json={"requisition_id": job.id}, headers=applicant_headers).json()["id"]
    _upload_real_resume(client, applicant_headers, application_id)

    hr_headers = auth_headers(client, hr_admin.email)
    # document-upload already auto-advances current_stage to
    # skill_matching, so only one more transition is needed.
    resp = client.post(
        f"/applications/{application_id}/transition", json={"target_stage": "interview_round_1"}, headers=hr_headers
    )
    assert resp.status_code == 200, resp.text

    db_session.add(RequisitionEvaluator(requisition_id=job.id, evaluator_id=evaluator.id))
    db_session.flush()
    resp = client.post(
        f"/hr/applications/{application_id}/interview-assignment",
        json={"stage_type": "interview_round_1", "evaluator_id": evaluator.id},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text

    eval_headers = auth_headers(client, evaluator.email)
    resp = client.get(f"/evaluator/applications/{application_id}/resume-file", headers=eval_headers)

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"


def test_evaluator_resume_file_404_when_not_assigned(client, applicant, hr_admin, evaluator, make_job):
    job = make_job(WORKFLOW)
    applicant_headers = auth_headers(client, applicant.email)
    application_id = client.post("/applications", json={"requisition_id": job.id}, headers=applicant_headers).json()["id"]
    _upload_real_resume(client, applicant_headers, application_id)

    eval_headers = auth_headers(client, evaluator.email)
    resp = client.get(f"/evaluator/applications/{application_id}/resume-file", headers=eval_headers)

    assert resp.status_code == 404, resp.text
