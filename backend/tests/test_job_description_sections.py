"""A job description's additional sections -- everything the document
says that the three fixed fields have no place for (salary, benefits,
documents to submit...).

What's under test: the AI reader keeps them, HR's create / edit /
replace carry them into the job and freeze a copy on each version, the
public board shows them, and none of it reaches the AI match -- so an
edit to the sections alone moves nobody's score and keeps the cached
embedding.
"""

from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select

from app.infra.config import settings
from app.models.job_description_version import JobDescriptionVersion
from app.schemas.job_description import JobDescriptionSection
from app.schemas.pipeline import JDExtractionCandidate
from app.services import skill_matching as sm
from tests.conftest import auth_headers
from tests.test_skill_matching import SIMPLE_WORKFLOW

_SAMPLE_PDF = next((Path(__file__).parent.parent / "uploads" / "resumes").glob("*.pdf"))

SALARY = {"title": "Salary", "content": "Salary Grade 11"}
DOCUMENTS = {"title": "Documents to Submit", "content": "Transcript of Records\nPersonal Data Sheet"}


def _hr(client):
    return auth_headers(client, "hr-test@arkivetesting.com")


def _versions(db_session, job) -> list[JobDescriptionVersion]:
    return list(
        db_session.scalars(
            select(JobDescriptionVersion)
            .where(JobDescriptionVersion.requisition_id == job.id)
            .order_by(JobDescriptionVersion.version)
        )
    )


def _job_with_sections(make_job, db_session, sections=(SALARY,)):
    job = make_job(
        SIMPLE_WORKFLOW,
        title="Data Analyst",
        description="Analyses enrolment data.",
        qualifications="BS Statistics",
        requirements="SQL",
    )
    job.additional_sections = [dict(s) for s in sections]
    job.embedding = [0.1, 0.2, 0.3]
    db_session.flush()
    return job


@patch("app.services.jd_extraction.ChatOpenAI.with_structured_output")
def test_extraction_returns_the_sections_and_drops_blank_ones(
    mock_llm, client, hr_admin, monkeypatch, job_description_uploads
):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_llm.return_value.invoke.return_value = JDExtractionCandidate(
        department="Testing",
        description="Verifies software quality across the platform.",
        qualifications="BS in Computer Science",
        requirements="Manual and automated testing",
        additional_sections=[
            JobDescriptionSection(**SALARY),
            JobDescriptionSection(title=" ", content=""),
        ],
        is_job_description=True,
        document_kind="job description",
        reason="",
    )
    with open(_SAMPLE_PDF, "rb") as f:
        resp = client.post(
            "/hr/requisitions/extract-jd",
            headers=_hr(client),
            data={"job_title": "QA Engineer"},
            files={"jd_file": ("qa-engineer.pdf", f, "application/pdf")},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["additional_sections"] == [SALARY]


def test_creating_a_job_keeps_its_sections_on_the_job_and_version_one(client, db_session, hr_admin):
    headers = _hr(client)
    created = client.post(
        "/hr/requisitions",
        headers=headers,
        json={
            "title": "Sections Role",
            "department": "Testing",
            "requirements": "Manual and automated testing",
            "additional_sections": [
                {"title": "  Salary ", "content": " Salary Grade 11 "},
                {"title": "", "content": "   "},
                DOCUMENTS,
            ],
            "workflow_preset": "standard",
            "publish": False,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    # trimmed, and the box left blank is gone
    assert body["additional_sections"] == [SALARY, DOCUMENTS]

    rows = [r for r in client.get("/hr/job-descriptions", headers=headers).json() if r["requisition_id"] == body["id"]]
    version = client.get(f"/hr/job-descriptions/{rows[0]['id']}", headers=headers).json()
    assert version["additional_sections"] == [SALARY, DOCUMENTS]


def test_a_job_created_without_sections_reads_as_none(client, hr_admin):
    created = client.post(
        "/hr/requisitions",
        headers=_hr(client),
        json={
            "title": "No Sections Role",
            "department": "Testing",
            "requirements": "SQL",
            "workflow_preset": "standard",
            "publish": False,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["additional_sections"] == []


def test_editing_only_the_sections_is_a_new_version_that_keeps_the_embedding(client, db_session, make_job):
    """The match never reads the sections, so the cached embedding of the
    scored text is still right and nobody's score is affected."""
    job = _job_with_sections(make_job, db_session)

    resp = client.patch(
        f"/hr/requisitions/{job.id}/job-description",
        headers=_hr(client),
        json={
            "description": "Analyses enrolment data.",
            "qualifications": "BS Statistics",
            "requirements": "SQL",
            "additional_sections": [SALARY, DOCUMENTS],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["additional_sections"] == [SALARY, DOCUMENTS]

    db_session.refresh(job)
    assert job.embedding == [0.1, 0.2, 0.3]
    v1, v2 = _versions(db_session, job)
    # the old version keeps the sections it put in force
    assert v1.additional_sections == [SALARY]
    assert v2.additional_sections == [SALARY, DOCUMENTS]


def test_an_edit_that_leaves_the_sections_out_keeps_them(client, db_session, make_job):
    """A page loaded before sections existed sends no such field. Saving
    a description edit from it must not wipe them."""
    job = _job_with_sections(make_job, db_session)

    resp = client.patch(
        f"/hr/requisitions/{job.id}/job-description",
        headers=_hr(client),
        json={"description": "Analyses enrolment data.", "qualifications": "BS Statistics", "requirements": "SQL\nPython"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["additional_sections"] == [SALARY]
    db_session.refresh(job)
    assert job.embedding is None  # the scored text did change
    assert _versions(db_session, job)[-1].additional_sections == [SALARY]


def test_an_edit_can_clear_the_sections(client, db_session, make_job):
    job = _job_with_sections(make_job, db_session)

    resp = client.patch(
        f"/hr/requisitions/{job.id}/job-description",
        headers=_hr(client),
        json={
            "description": "Analyses enrolment data.",
            "qualifications": "BS Statistics",
            "requirements": "SQL",
            "additional_sections": [],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["additional_sections"] == []


def test_an_edit_with_the_same_sections_and_text_is_refused(client, db_session, make_job):
    job = _job_with_sections(make_job, db_session)

    resp = client.patch(
        f"/hr/requisitions/{job.id}/job-description",
        headers=_hr(client),
        json={
            "description": "Analyses enrolment data.",
            "qualifications": "BS Statistics",
            "requirements": "SQL",
            "additional_sections": [{"title": " Salary", "content": "Salary Grade 11 "}],
        },
    )
    assert resp.status_code == 409
    assert len(_versions(db_session, job)) <= 1


def test_sections_alone_cannot_stand_in_for_the_job_description(client, db_session, make_job):
    """The AI match reads the three fields. Sections don't count towards
    having a job description at all."""
    job = _job_with_sections(make_job, db_session)

    resp = client.patch(
        f"/hr/requisitions/{job.id}/job-description",
        headers=_hr(client),
        json={"description": "", "qualifications": "", "requirements": "", "additional_sections": [SALARY]},
    )
    assert resp.status_code == 422


def test_a_replacement_carries_its_sections(client, db_session, make_job):
    job = _job_with_sections(make_job, db_session)

    resp = client.post(
        f"/hr/requisitions/{job.id}/job-description",
        headers=_hr(client),
        json={
            "description": "Analyses enrolment data.",
            "qualifications": "BS Statistics",
            "requirements": "SQL",
            "additional_sections": [DOCUMENTS],
            "confirm_title": "Data Analyst",
        },
    )
    assert resp.status_code == 201, resp.text
    db_session.refresh(job)
    assert job.additional_sections == [DOCUMENTS]
    assert _versions(db_session, job)[-1].additional_sections == [DOCUMENTS]


def test_the_public_board_shows_the_sections(client, db_session, make_job):
    job = _job_with_sections(make_job, db_session, sections=(SALARY, DOCUMENTS))

    detail = client.get(f"/public/jobs/{job.id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["additional_sections"] == [SALARY, DOCUMENTS]

    listed = client.get("/public/jobs", params={"q": "Analyses enrolment data"}).json()["items"]
    mine = next(item for item in listed if item["id"] == job.id)
    assert mine["additional_sections"] == [SALARY, DOCUMENTS]


def test_the_match_never_reads_the_sections(db_session, make_job):
    job = _job_with_sections(make_job, db_session, sections=(SALARY, DOCUMENTS))

    corpus = sm._requisition_corpus_text(job)
    assert "Salary Grade 11" not in corpus
    assert "Transcript of Records" not in corpus
    assert not any("Transcript" in chunk for chunk in sm._chunk_jd_requirements(job))
