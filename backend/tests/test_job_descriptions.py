"""Job-description history and replacement.

The promise under test: HR can put a new job description in force, but
nobody already scored is affected -- their stored score, measured
against the old text, stays exactly as it was and says which version it
used -- while the next applicant is measured against the new text.
Plus the guard rails around that: the typed-title confirmation (checked
on the server, not only in the dialog), no empty "replacements", and a
document id that can't be forged or reused.
"""

from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select

from app.infra.config import settings
from app.models.enums import StageType
from app.models.job_description_version import JobDescriptionVersion
from app.models.job_requisition import JobRequisition
from app.models.stage_instance import StageInstance
from app.schemas.pipeline import JDExtractionCandidate
from app.services import skill_matching as sm
from app.services.job_descriptions import current_version_number
from tests.conftest import auth_headers
from tests.test_skill_matching import SIMPLE_WORKFLOW, _setup, _structured_output_by_schema

_SAMPLE_PDF = next((Path(__file__).parent.parent / "uploads" / "resumes").glob("*.pdf"))


def _hr(client):
    return auth_headers(client, "hr-test@arkivetesting.com")


def _extract(client, headers, mock_llm, monkeypatch) -> str:
    """Runs extract-jd on the sample PDF and returns the upload id."""
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_llm.return_value.invoke.return_value = JDExtractionCandidate(
        department="Testing",
        description="Verifies software quality across the platform.",
        qualifications="BS in Computer Science",
        requirements="Manual and automated testing",
        is_job_description=True,
        document_kind="job description",
        reason="",
    )
    with open(_SAMPLE_PDF, "rb") as f:
        resp = client.post(
            "/hr/requisitions/extract-jd",
            headers=headers,
            data={"job_title": "QA Engineer"},
            files={"jd_file": ("qa-engineer.pdf", f, "application/pdf")},
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["jd_upload_id"]


def _score(db_session, application, *, match_score: float, jd_version: int | None = None) -> StageInstance:
    instance = db_session.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.skill_matching,
        )
    )
    payload = {"match_score": match_score, "strengths": ["Python"], "flagged": False}
    if jd_version is not None:
        payload["jd_version"] = jd_version
    instance.payload = payload
    db_session.flush()
    return instance


def _versions(db_session, job) -> list[JobDescriptionVersion]:
    return list(
        db_session.scalars(
            select(JobDescriptionVersion)
            .where(JobDescriptionVersion.requisition_id == job.id)
            .order_by(JobDescriptionVersion.version)
        )
    )


# --------------------------------------------------------------- keeping the PDF


@patch("app.services.jd_extraction.ChatOpenAI.with_structured_output")
def test_extraction_keeps_the_pdf_and_creation_records_it_as_version_one(
    mock_llm, client, hr_admin, monkeypatch, job_description_uploads
):
    headers = _hr(client)
    upload_id = _extract(client, headers, mock_llm, monkeypatch)
    assert (job_description_uploads / f"{upload_id}.pdf").read_bytes() == _SAMPLE_PDF.read_bytes()

    created = client.post(
        "/hr/requisitions",
        headers=headers,
        json={
            "title": "QA Engineer",
            "department": "Testing",
            "requirements": "Manual and automated testing",
            "jd_filename": "qa-engineer.pdf",
            "jd_upload_id": upload_id,
            "workflow_preset": "standard",
            "publish": False,
        },
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    rows = [r for r in client.get("/hr/job-descriptions", headers=headers).json() if r["requisition_id"] == job_id]
    assert len(rows) == 1
    row = rows[0]
    assert (row["version"], row["is_current"], row["has_file"]) == (1, True, True)
    assert row["original_filename"] == "qa-engineer.pdf"
    assert row["file_size"] == _SAMPLE_PDF.stat().st_size

    download = client.get(f"/hr/job-descriptions/{row['id']}/file", headers=headers)
    assert download.status_code == 200
    assert download.content == _SAMPLE_PDF.read_bytes()


def test_a_forged_upload_id_is_refused_and_creates_nothing(client, db_session, hr_admin):
    headers = _hr(client)
    for bogus in ("../../etc/passwd", "0" * 32):
        resp = client.post(
            "/hr/requisitions",
            headers=headers,
            json={
                "title": "Forged Upload Role",
                "department": "Testing",
                "jd_upload_id": bogus,
                "workflow_preset": "standard",
                "publish": False,
            },
        )
        assert resp.status_code == 422, resp.text
    assert db_session.scalar(select(JobRequisition).where(JobRequisition.title == "Forged Upload Role")) is None


def test_a_job_typed_by_hand_has_a_version_with_no_file(client, hr_admin):
    headers = _hr(client)
    job_id = client.post(
        "/hr/requisitions",
        headers=headers,
        json={"title": "Typed Role", "department": "Testing", "workflow_preset": "standard", "publish": False},
    ).json()["id"]

    row = next(r for r in client.get("/hr/job-descriptions", headers=headers).json() if r["requisition_id"] == job_id)
    assert row["has_file"] is False
    assert client.get(f"/hr/job-descriptions/{row['id']}/file", headers=headers).status_code == 404


def test_jobs_created_outside_the_api_get_their_version_one_on_first_read(client, db_session, make_job):
    """The seed script and fixtures insert jobs directly; the history must
    still show them rather than leave them with nothing to replace."""
    job = make_job(SIMPLE_WORKFLOW, title="Seeded Role", requirements="SQL")
    assert _versions(db_session, job) == []

    rows = client.get("/hr/job-descriptions", headers=_hr(client)).json()
    assert [(r["version"], r["is_current"]) for r in rows if r["requisition_id"] == job.id] == [(1, True)]


def test_only_hr_can_read_the_history(client, applicant):
    headers = auth_headers(client, "applicant-test@arkivetesting.com")
    assert client.get("/hr/job-descriptions", headers=headers).status_code == 403


# -------------------------------------------------------------------- replacing


def test_replacement_is_refused_without_the_job_title(client, db_session, make_job):
    job = make_job(SIMPLE_WORKFLOW, title="Data Analyst", requirements="SQL")
    resp = client.post(
        f"/hr/requisitions/{job.id}/job-description",
        headers=_hr(client),
        json={"requirements": "SQL and Python", "confirm_title": "Data"},
    )
    assert resp.status_code == 422
    assert "Data Analyst" in resp.json()["detail"]
    db_session.refresh(job)
    assert job.requirements == "SQL"


def test_a_replacement_that_changes_nothing_is_refused(client, db_session, make_job):
    job = make_job(SIMPLE_WORKFLOW, title="Data Analyst", requirements="SQL")
    resp = client.post(
        f"/hr/requisitions/{job.id}/job-description",
        headers=_hr(client),
        json={"requirements": "  SQL  ", "confirm_title": "data analyst"},
    )
    assert resp.status_code == 409
    assert len(_versions(db_session, job)) <= 1


def test_replacing_keeps_every_existing_score_and_measures_new_applicants_against_the_new_text(
    client, db_session, make_job, make_application
):
    job = make_job(
        SIMPLE_WORKFLOW,
        title="Data Analyst",
        description="Analyses enrolment data.",
        qualifications="BS Statistics",
        requirements="SQL",
    )
    job.embedding = [0.1, 0.2, 0.3]
    # scored before versions existed: no jd_version in the payload
    scored = _score(db_session, make_application(job), match_score=74.5)
    before = dict(scored.payload)

    resp = client.post(
        f"/hr/requisitions/{job.id}/job-description",
        headers=_hr(client),
        json={
            "description": "Analyses enrolment and retention data.",
            "qualifications": "BS Statistics",
            "requirements": "SQL\nPython",
            "change_note": "Added Python after the department's review",
            "confirm_title": "Data Analyst",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["version"] == 2
    assert resp.json()["is_current"] is True
    assert resp.json()["scored_count"] == 0

    db_session.refresh(job)
    db_session.refresh(scored)
    # the job now carries the new text, and its cached embedding of the
    # old text is gone, so the next applicant is embedded against the new
    assert job.requirements == "SQL\nPython"
    assert job.embedding is None
    assert current_version_number(db_session, job.id) == 2
    # the applicant already scored is untouched -- no re-scoring
    assert scored.payload == before

    v1, v2 = _versions(db_session, job)
    assert v1.replaced_at is not None and v2.replaced_at is None
    assert (v1.requirements, v2.requirements) == ("SQL", "SQL\nPython")
    assert v2.change_note == "Added Python after the department's review"

    rows = {r["version"]: r for r in client.get("/hr/job-descriptions", headers=_hr(client)).json() if r["requisition_id"] == job.id}
    assert rows[1]["scored_count"] == 1 and rows[1]["is_current"] is False
    assert rows[2]["scored_count"] == 0 and rows[2]["is_current"] is True

    # the old version's text is still readable -- what that applicant was
    # actually measured against
    detail = client.get(f"/hr/job-descriptions/{rows[1]['id']}", headers=_hr(client)).json()
    assert detail["requirements"] == "SQL"
    assert detail["scored_count"] == 1


# ------------------------------------------------------- editing in place


def test_editing_in_place_is_a_new_version_measured_like_any_replacement(client, db_session, make_job):
    """The job opening page's Edit: no typed title, but otherwise exactly
    a replacement -- the old text kept in the history, the cached
    embedding cleared so the next applicant is measured against the new
    text."""
    job = make_job(
        SIMPLE_WORKFLOW,
        title="Data Analyst",
        description="Analyses enrolment data.",
        qualifications="BS Statistics",
        requirements="SQL",
    )
    job.embedding = [0.1, 0.2, 0.3]
    db_session.flush()

    resp = client.patch(
        f"/hr/requisitions/{job.id}/job-description",
        headers=_hr(client),
        json={
            "description": "Analyses enrolment data.",
            "qualifications": "BS Statistics",
            "requirements": "SQL\nPython",
            "change_note": "Added Python",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["requirements"] == "SQL\nPython"

    db_session.refresh(job)
    assert job.requirements == "SQL\nPython"
    assert job.embedding is None
    v1, v2 = _versions(db_session, job)
    assert (v1.requirements, v2.requirements) == ("SQL", "SQL\nPython")
    assert v1.replaced_at is not None and v2.replaced_at is None
    assert v2.change_note == "Added Python"


def test_editing_in_place_is_locked_while_anyone_is_active(client, db_session, make_job, make_application):
    """Same rule as the stage order: one active candidate locks it."""
    job = make_job(SIMPLE_WORKFLOW, title="Data Analyst", requirements="SQL")
    job.embedding = [0.1, 0.2, 0.3]
    make_application(job)
    db_session.flush()

    resp = client.patch(
        f"/hr/requisitions/{job.id}/job-description",
        headers=_hr(client),
        json={"requirements": "SQL\nPython"},
    )
    assert resp.status_code == 409
    assert "active candidates" in resp.json()["detail"]
    db_session.refresh(job)
    assert job.requirements == "SQL"
    assert job.embedding == [0.1, 0.2, 0.3]
    assert len(_versions(db_session, job)) <= 1


def test_editing_in_place_unlocks_once_nobody_is_active(client, db_session, make_job, make_application):
    """Rejected, withdrawn or hired applicants don't hold the lock -- the
    stage order doesn't count them either. Their stored scores keep
    naming the version they were measured against."""
    from app.models.enums import ApplicationStatus

    job = make_job(SIMPLE_WORKFLOW, title="Data Analyst", requirements="SQL")
    application = make_application(job)
    scored = _score(db_session, application, match_score=74.5, jd_version=1)
    before = dict(scored.payload)
    application.status = ApplicationStatus.rejected
    db_session.flush()

    resp = client.patch(
        f"/hr/requisitions/{job.id}/job-description",
        headers=_hr(client),
        json={"requirements": "SQL\nPython"},
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(scored)
    assert scored.payload == before


def test_an_edit_that_changes_nothing_is_refused(client, db_session, make_job):
    job = make_job(SIMPLE_WORKFLOW, title="Data Analyst", requirements="SQL")
    resp = client.patch(
        f"/hr/requisitions/{job.id}/job-description",
        headers=_hr(client),
        json={"requirements": "  SQL  "},
    )
    assert resp.status_code == 409
    assert len(_versions(db_session, job)) <= 1


def test_an_edit_cannot_empty_the_job_description(client, db_session, make_job):
    """The AI match reads these three fields. Emptying all of them would
    score every applicant against the title alone."""
    job = make_job(SIMPLE_WORKFLOW, title="Data Analyst", requirements="SQL")
    resp = client.patch(
        f"/hr/requisitions/{job.id}/job-description",
        headers=_hr(client),
        json={"description": " ", "qualifications": "", "requirements": None},
    )
    assert resp.status_code == 422
    db_session.refresh(job)
    assert job.requirements == "SQL"


def test_only_hr_can_edit_in_place(client, make_job, applicant):
    job = make_job(SIMPLE_WORKFLOW, title="Data Analyst", requirements="SQL")
    resp = client.patch(
        f"/hr/requisitions/{job.id}/job-description",
        headers=auth_headers(client, applicant.email),
        json={"requirements": "SQL\nPython"},
    )
    assert resp.status_code == 403


@patch("app.services.jd_extraction.ChatOpenAI.with_structured_output")
def test_a_document_can_only_back_one_version(mock_llm, client, db_session, make_job, monkeypatch):
    headers = _hr(client)
    upload_id = _extract(client, headers, mock_llm, monkeypatch)
    first = make_job(SIMPLE_WORKFLOW, title="First Role", requirements="A")
    second = make_job(SIMPLE_WORKFLOW, title="Second Role", requirements="B")

    ok = client.post(
        f"/hr/requisitions/{first.id}/job-description",
        headers=headers,
        json={"requirements": "A2", "jd_upload_id": upload_id, "jd_filename": "jd.pdf", "confirm_title": "First Role"},
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["has_file"] is True

    reused = client.post(
        f"/hr/requisitions/{second.id}/job-description",
        headers=headers,
        json={"requirements": "B2", "jd_upload_id": upload_id, "confirm_title": "Second Role"},
    )
    assert reused.status_code == 422


@patch("app.services.skill_matching.ChatOpenAI.with_structured_output")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_query")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_documents")
def test_a_new_score_names_the_version_it_was_measured_against(
    mock_embed_documents,
    mock_embed_query,
    mock_with_structured_output,
    client,
    db_session,
    make_job,
    make_application,
    make_resume,
    monkeypatch,
):
    monkeypatch.setattr(sm.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(sm, "_get_or_compute_resume_embedding", lambda embeddings, resume: [1.0, 0.0, 0.0])
    monkeypatch.setattr(sm, "_get_or_compute_requisition_embedding", lambda embeddings, requisition: [1.0, 0.0, 0.0])
    mock_embed_documents.side_effect = lambda texts: [[1.0, 0.0, 0.0] for _ in texts]
    mock_embed_query.return_value = [1.0, 0.0, 0.0]
    _structured_output_by_schema(mock_with_structured_output)

    job, resume = _setup(db_session, make_job, make_application, make_resume)
    assert sm.run_skill_matching(db_session, resume=resume, target_requisition=job).jd_version == 1

    resp = client.post(
        f"/hr/requisitions/{job.id}/job-description",
        headers=_hr(client),
        json={"requirements": "Experience with FastAPI and PostgreSQL", "confirm_title": job.title},
    )
    assert resp.status_code == 201, resp.text
    assert sm.run_skill_matching(db_session, resume=resume, target_requisition=job).jd_version == 2


# --------------------------------------------------------------------- deleting


@patch("app.services.jd_extraction.ChatOpenAI.with_structured_output")
def test_deleting_a_job_removes_its_versions_and_their_documents(
    mock_llm, client, db_session, hr_admin, monkeypatch, job_description_uploads
):
    headers = _hr(client)
    upload_id = _extract(client, headers, mock_llm, monkeypatch)
    job_id = client.post(
        "/hr/requisitions",
        headers=headers,
        json={
            "title": "Short-Lived Role",
            "department": "Testing",
            "jd_filename": "qa-engineer.pdf",
            "jd_upload_id": upload_id,
            "workflow_preset": "standard",
            "publish": False,
        },
    ).json()["id"]
    stored = job_description_uploads / f"{upload_id}.pdf"
    assert stored.exists()

    assert client.delete(f"/hr/requisitions/{job_id}", headers=headers).status_code == 204
    assert db_session.scalars(
        select(JobDescriptionVersion).where(JobDescriptionVersion.requisition_id == job_id)
    ).all() == []
    assert not stored.exists()
