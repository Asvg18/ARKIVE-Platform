"""Coverage for two applicant-initiated actions: "Cancel Application"
(withdraw) and "Add More Documents" (supplemental documents added after
the initial document_upload submission)."""

import json
from pathlib import Path

from app.infra.uploads import MAX_UPLOAD_BYTES
from tests.conftest import auth_headers

WORKFLOW = ["document_upload", "skill_matching", "final_decision"]
_SAMPLE_RESUME_PDF = next((Path(__file__).parent.parent / "uploads" / "resumes").glob("*.pdf"))

_MINIMAL_RESUME_DATA = {
    "full_name": "Ada Applicant",
    "email": "applicant-test@arkivetesting.com",
    "phone": "",
    "location": "",
    "linkedin_url": "",
    "portfolio_url": "",
    "professional_summary": "",
    "education": [],
    "experience": [],
    "skills": [],
    "certifications": [],
}


def _apply(client, applicant, make_job) -> tuple[int, dict]:
    job = make_job(WORKFLOW)
    headers = auth_headers(client, applicant.email)
    application_id = client.post("/applications", json={"requisition_id": job.id}, headers=headers).json()["id"]
    return application_id, headers


# --- Withdraw ---------------------------------------------------------


def test_withdraw_sets_status_to_withdrawn(client, applicant, make_job):
    application_id, headers = _apply(client, applicant, make_job)

    resp = client.post(f"/applicant/applications/{application_id}/withdraw", headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "withdrawn"


def test_withdraw_freezes_further_stage_progress(client, applicant, make_job):
    application_id, headers = _apply(client, applicant, make_job)
    client.post(f"/applicant/applications/{application_id}/withdraw", headers=headers)

    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        resp = client.post(
            f"/applicant/applications/{application_id}/document-upload",
            headers=headers,
            files={"resume_file": ("resume.pdf", f, "application/pdf")},
            data={"resume_data": json.dumps(_MINIMAL_RESUME_DATA)},
        )

    assert resp.status_code == 422, resp.text
    assert "withdrawn" in resp.json()["detail"].lower()


def test_withdraw_rejects_already_non_active_application(client, applicant, make_job):
    application_id, headers = _apply(client, applicant, make_job)
    client.post(f"/applicant/applications/{application_id}/withdraw", headers=headers)

    resp = client.post(f"/applicant/applications/{application_id}/withdraw", headers=headers)

    assert resp.status_code == 409


def test_withdraw_rejects_wrong_owner(client, applicant, make_job, make_user):
    from app.models.enums import UserRole

    application_id, _ = _apply(client, applicant, make_job)
    other = make_user("other-applicant@arkivetesting.com", UserRole.applicant)
    other_headers = auth_headers(client, other.email)

    resp = client.post(f"/applicant/applications/{application_id}/withdraw", headers=other_headers)

    assert resp.status_code == 404


# --- Add More Documents -------------------------------------------------


def test_upload_supplemental_document_appears_on_application_detail(client, applicant, make_job):
    application_id, headers = _apply(client, applicant, make_job)

    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        resp = client.post(
            f"/applicant/applications/{application_id}/documents",
            headers=headers,
            files={"file": ("reference-letter.pdf", f, "application/pdf")},
            data={"label": "Reference Letter"},
        )

    assert resp.status_code == 200, resp.text
    documents = resp.json()["documents"]
    assert len(documents) == 1
    assert documents[0]["label"] == "Reference Letter"
    assert documents[0]["original_filename"] == "reference-letter.pdf"


def test_upload_supplemental_document_requires_a_label(client, applicant, make_job):
    application_id, headers = _apply(client, applicant, make_job)

    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        resp = client.post(
            f"/applicant/applications/{application_id}/documents",
            headers=headers,
            files={"file": ("portfolio.pdf", f, "application/pdf")},
            data={"label": "   "},
        )

    assert resp.status_code == 422


def test_upload_supplemental_document_rejected_once_withdrawn(client, applicant, make_job):
    application_id, headers = _apply(client, applicant, make_job)
    client.post(f"/applicant/applications/{application_id}/withdraw", headers=headers)

    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        resp = client.post(
            f"/applicant/applications/{application_id}/documents",
            headers=headers,
            files={"file": ("portfolio.pdf", f, "application/pdf")},
            data={"label": "Portfolio"},
        )

    assert resp.status_code == 409


def test_applicant_can_download_own_supplemental_document(client, applicant, make_job):
    application_id, headers = _apply(client, applicant, make_job)
    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        upload = client.post(
            f"/applicant/applications/{application_id}/documents",
            headers=headers,
            files={"file": ("portfolio.pdf", f, "application/pdf")},
            data={"label": "Portfolio"},
        )
    document_id = upload.json()["documents"][0]["id"]

    resp = client.get(
        f"/applicant/applications/{application_id}/documents/{document_id}/file", headers=headers
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


def test_download_supplemental_document_rejects_wrong_owner(client, applicant, make_job, make_user):
    from app.models.enums import UserRole

    application_id, headers = _apply(client, applicant, make_job)
    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        upload = client.post(
            f"/applicant/applications/{application_id}/documents",
            headers=headers,
            files={"file": ("portfolio.pdf", f, "application/pdf")},
            data={"label": "Portfolio"},
        )
    document_id = upload.json()["documents"][0]["id"]
    other = make_user("other-applicant-2@arkivetesting.com", UserRole.applicant)
    other_headers = auth_headers(client, other.email)

    resp = client.get(
        f"/applicant/applications/{application_id}/documents/{document_id}/file", headers=other_headers
    )

    assert resp.status_code == 404


def test_hr_profile_includes_supplemental_documents(client, applicant, hr_admin, make_job):
    application_id, headers = _apply(client, applicant, make_job)
    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        client.post(
            f"/applicant/applications/{application_id}/documents",
            headers=headers,
            files={"file": ("reference-letter.pdf", f, "application/pdf")},
            data={"label": "Reference Letter"},
        )

    hr_headers = auth_headers(client, hr_admin.email)
    profile = client.get(f"/hr/applications/{application_id}/profile", headers=hr_headers).json()

    assert len(profile["documents"]) == 1
    assert profile["documents"][0]["label"] == "Reference Letter"


def test_hr_can_download_candidate_supplemental_document(client, applicant, hr_admin, make_job):
    application_id, headers = _apply(client, applicant, make_job)
    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        upload = client.post(
            f"/applicant/applications/{application_id}/documents",
            headers=headers,
            files={"file": ("reference-letter.pdf", f, "application/pdf")},
            data={"label": "Reference Letter"},
        )
    document_id = upload.json()["documents"][0]["id"]
    hr_headers = auth_headers(client, hr_admin.email)

    resp = client.get(
        f"/hr/applications/{application_id}/documents/{document_id}/file", headers=hr_headers
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


# --- Upload size ceiling ----------------------------------------------
#
# easy to believe this gap was already covered, since a huge junk file
# *is* rejected -- but only for failing to parse as a PDF. a file that's
# both valid and enormous had nothing standing in its way, and
# backend/uploads/ has no quota and shares a disk with the database.


def _oversized_pdf() -> bytes:
    """A real PDF header followed by enough filler to break the ceiling,
    so the request is refused for its size and not for its format."""
    body = _SAMPLE_RESUME_PDF.read_bytes()
    padding = b"\n%" + b"A" * (MAX_UPLOAD_BYTES + 1024)
    return body + padding


def test_a_valid_but_enormous_pdf_is_refused(client, applicant, make_job):
    application_id, headers = _apply(client, applicant, make_job)

    resp = client.post(
        f"/applicant/applications/{application_id}/documents",
        headers=headers,
        files={"file": ("huge.pdf", _oversized_pdf(), "application/pdf")},
        data={"label": "Reference Letter"},
    )

    assert resp.status_code == 413, resp.text
    # The message has to name the limit, or the applicant cannot tell
    # "slightly too big" from "wrong kind of file".
    assert "10 MB" in resp.json()["detail"]


def test_the_refused_upload_is_not_stored(client, applicant, make_job):
    application_id, headers = _apply(client, applicant, make_job)

    client.post(
        f"/applicant/applications/{application_id}/documents",
        headers=headers,
        files={"file": ("huge.pdf", _oversized_pdf(), "application/pdf")},
        data={"label": "Reference Letter"},
    )

    detail = client.get(f"/applicant/applications/{application_id}", headers=headers).json()
    assert detail["documents"] == []


def test_an_ordinary_document_is_unaffected_by_the_ceiling(client, applicant, make_job):
    """The limit is far above real use; the guard must not be so eager
    that it refuses the files the system exists to collect."""
    application_id, headers = _apply(client, applicant, make_job)

    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        resp = client.post(
            f"/applicant/applications/{application_id}/documents",
            headers=headers,
            files={"file": ("reference-letter.pdf", f, "application/pdf")},
            data={"label": "Reference Letter"},
        )

    assert resp.status_code == 200, resp.text
