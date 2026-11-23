"""Black-box tests for the applicant-facing API surface -- apply, resume
extraction/upload, pre-screening submission, scheduling, and onboarding.
No prior coverage of any of this existed; this covers the full
document_upload -> skill_matching -> ... -> onboarding path at least
once, plus ownership checks, same real-endpoint-through-client style as
test_evaluator.py/test_transitions.py."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import select

from app.infra.config import settings
from app.models.enums import RequisitionStatus, StageType, UserRole
from app.models.exam_slot import ExamSlot
from app.models.exam_slot_booking import ExamSlotBooking
from app.schemas.resume import ResumeExtractionResult
from app.schemas.skill_match import AuditVerdict, SkillMatchAnalysis
from app.schemas.skill_match import RecheckResult, VerdictAuditResult
from tests.conftest import auth_headers

WORKFLOW = ["document_upload", "skill_matching", "final_decision"]
_SAMPLE_RESUME_PDF = next((Path(__file__).parent.parent / "uploads" / "resumes").glob("*.pdf"))

_RESUME_DATA = {
    "full_name": "Ada Applicant",
    "email": "applicant-test@arkivetesting.com",
    "phone": "09171234567",
    "location": "Lucena City",
    "linkedin_url": "",
    "portfolio_url": "",
    "professional_summary": "QA-focused engineer.",
    "education": [
        {"school": "MSEUF", "degree": "BS", "field_of_study": "Computer Science", "start_date": "2015", "end_date": "2019", "honors": ""}
    ],
    "experience": [
        {"company": "Acme", "title": "QA Engineer", "start_date": "2019", "end_date": "Present", "description": "Manual and automated testing."}
    ],
    "skills": ["Testing", "QA", "Python"],
    "certifications": [],
}


def _skill_matching_models(mock_with_structured_output, analysis: SkillMatchAnalysis) -> None:
    """Point the Skill Matching Agent's mocked model at the right answer
    for each schema it asks about.

    Its qualitative half runs as a graph of six agents now, two of which
    call a model: the Scoring Agent writes the assessment and the Critic
    Agent audits it (services/rag_pipeline.py). A single return value
    would hand the Critic a SkillMatchAnalysis and then ask it whether it
    `is_grounded`.

    The Critic passes here on purpose -- these are tests about the
    applicant's path through the API, so the pipeline's happy path is
    what keeps them measuring that rather than the retry cycle.
    """
    results = {"SkillMatchAnalysis": analysis, "AuditVerdict": AuditVerdict(is_grounded=True), "VerdictAuditResult": VerdictAuditResult(), "RecheckResult": RecheckResult()}
    mock_with_structured_output.side_effect = lambda schema, **kw: SimpleNamespace(
        invoke=lambda messages: results[schema.__name__]
    )


def _fake_resume() -> ResumeExtractionResult:
    return ResumeExtractionResult(**_RESUME_DATA)


def test_apply_creates_application_at_first_stage(client, applicant, make_job):
    job = make_job(WORKFLOW)
    headers = auth_headers(client, applicant.email)

    resp = client.post("/applications", json={"requisition_id": job.id}, headers=headers)

    assert resp.status_code == 201, resp.text
    assert resp.json()["current_stage"] == "document_upload"
    assert resp.json()["status"] == "active"
    # the job browser marks positions already applied to by this
    assert resp.json()["requisition_id"] == job.id


def test_apply_rejects_duplicate_application(client, applicant, make_job):
    job = make_job(WORKFLOW)
    headers = auth_headers(client, applicant.email)
    client.post("/applications", json={"requisition_id": job.id}, headers=headers)

    resp = client.post("/applications", json={"requisition_id": job.id}, headers=headers)

    assert resp.status_code == 409


def test_apply_rejects_draft_job(client, applicant, db_session, make_job):
    job = make_job(WORKFLOW)
    job.status = RequisitionStatus.draft
    db_session.flush()
    headers = auth_headers(client, applicant.email)

    resp = client.post("/applications", json={"requisition_id": job.id}, headers=headers)

    assert resp.status_code == 404


@patch("app.services.resume_extraction.ChatOpenAI.with_structured_output")
def test_resume_extract_preview_returns_parsed_fields(mock_llm, client, applicant, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_llm.return_value.invoke.return_value = _fake_resume()
    headers = auth_headers(client, applicant.email)

    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        resp = client.post(
            "/applicant/resume/extract",
            headers=headers,
            files={"resume_file": ("resume.pdf", f, "application/pdf")},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["full_name"] == "Ada Applicant"
    assert resp.json()["skills"] == ["Testing", "QA", "Python"]


def test_document_upload_advances_to_skill_matching(client, applicant, make_job):
    job = make_job(WORKFLOW)
    headers = auth_headers(client, applicant.email)
    application_id = client.post("/applications", json={"requisition_id": job.id}, headers=headers).json()["id"]

    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        resp = client.post(
            f"/applicant/applications/{application_id}/document-upload",
            headers=headers,
            files={"resume_file": ("resume.pdf", f, "application/pdf")},
            data={"resume_data": json.dumps(_RESUME_DATA)},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["current_stage"] == "skill_matching"
    stage_one = next(s for s in resp.json()["stage_instances"] if s["stage_type"] == "document_upload")
    assert stage_one["status"] == "complete"


def test_document_upload_letter_of_intent_surfaces_on_hr_profile(client, applicant, hr_admin, make_job):
    """Optional free text captured alongside the resume, surfaced to HR
    on the Candidate Profile."""
    job = make_job(WORKFLOW)
    headers = auth_headers(client, applicant.email)
    application_id = client.post("/applications", json={"requisition_id": job.id}, headers=headers).json()["id"]

    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        resp = client.post(
            f"/applicant/applications/{application_id}/document-upload",
            headers=headers,
            files={"resume_file": ("resume.pdf", f, "application/pdf")},
            data={"resume_data": json.dumps(_RESUME_DATA), "letter_of_intent": "I am excited to apply."},
        )
    assert resp.status_code == 200, resp.text

    hr_headers = auth_headers(client, hr_admin.email)
    profile = client.get(f"/hr/applications/{application_id}/profile", headers=hr_headers).json()
    assert profile["letter_of_intent"] == "I am excited to apply."


def test_document_upload_without_letter_of_intent_leaves_it_null(client, applicant, hr_admin, make_job):
    job = make_job(WORKFLOW)
    headers = auth_headers(client, applicant.email)
    application_id = client.post("/applications", json={"requisition_id": job.id}, headers=headers).json()["id"]

    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        client.post(
            f"/applicant/applications/{application_id}/document-upload",
            headers=headers,
            files={"resume_file": ("resume.pdf", f, "application/pdf")},
            data={"resume_data": json.dumps(_RESUME_DATA)},
        )

    hr_headers = auth_headers(client, hr_admin.email)
    profile = client.get(f"/hr/applications/{application_id}/profile", headers=hr_headers).json()
    assert profile["letter_of_intent"] is None


def test_document_upload_keeps_additional_sections_for_hr(client, applicant, hr_admin, make_job):
    """Sections the fixed fields have no place for are stored as the
    applicant left them and reach HR's copy of the resume."""
    job = make_job(WORKFLOW)
    headers = auth_headers(client, applicant.email)
    application_id = client.post("/applications", json={"requisition_id": job.id}, headers=headers).json()["id"]
    sections = [
        {"title": "Projects", "content": "ARKIVE -- HR recruitment platform\nCampus event tracker"},
        {"title": "Awards", "content": "Dean's Lister, 2024"},
    ]

    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        resp = client.post(
            f"/applicant/applications/{application_id}/document-upload",
            headers=headers,
            files={"resume_file": ("resume.pdf", f, "application/pdf")},
            data={"resume_data": json.dumps({**_RESUME_DATA, "additional_sections": sections})},
        )
    assert resp.status_code == 200, resp.text

    hr_headers = auth_headers(client, hr_admin.email)
    profile = client.get(f"/hr/applications/{application_id}/profile", headers=hr_headers).json()
    assert profile["resume"]["additional_sections"] == sections


def test_document_upload_without_additional_sections_reads_as_none(client, applicant, hr_admin, make_job):
    """A submission from before the field existed still goes through."""
    job = make_job(WORKFLOW)
    headers = auth_headers(client, applicant.email)
    application_id = client.post("/applications", json={"requisition_id": job.id}, headers=headers).json()["id"]
    assert "additional_sections" not in _RESUME_DATA

    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        resp = client.post(
            f"/applicant/applications/{application_id}/document-upload",
            headers=headers,
            files={"resume_file": ("resume.pdf", f, "application/pdf")},
            data={"resume_data": json.dumps(_RESUME_DATA)},
        )
    assert resp.status_code == 200, resp.text

    hr_headers = auth_headers(client, hr_admin.email)
    profile = client.get(f"/hr/applications/{application_id}/profile", headers=hr_headers).json()
    assert profile["resume"]["additional_sections"] == []


def test_document_upload_rejects_malformed_resume_data(client, applicant, make_job):
    job = make_job(WORKFLOW)
    headers = auth_headers(client, applicant.email)
    application_id = client.post("/applications", json={"requisition_id": job.id}, headers=headers).json()["id"]

    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        resp = client.post(
            f"/applicant/applications/{application_id}/document-upload",
            headers=headers,
            files={"resume_file": ("resume.pdf", f, "application/pdf")},
            data={"resume_data": "{}"},
        )

    assert resp.status_code == 422


def test_document_upload_rejects_wrong_owner(client, applicant, make_job, make_user):
    job = make_job(WORKFLOW)
    headers = auth_headers(client, applicant.email)
    application_id = client.post("/applications", json={"requisition_id": job.id}, headers=headers).json()["id"]

    other_applicant = make_user("other-applicant-test@arkivetesting.com", UserRole.applicant)
    other_headers = auth_headers(client, other_applicant.email)

    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        resp = client.post(
            f"/applicant/applications/{application_id}/document-upload",
            headers=other_headers,
            files={"resume_file": ("resume.pdf", f, "application/pdf")},
            data={"resume_data": json.dumps(_RESUME_DATA)},
        )

    assert resp.status_code == 404


@patch("app.services.skill_matching.ChatOpenAI.with_structured_output")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_query")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_documents")
def test_pre_screening_submission_advances_when_no_questions_configured(
    mock_embed_documents, mock_embed_query, mock_with_structured_output, client, applicant, db_session, make_job, monkeypatch
):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_embed_documents.side_effect = lambda texts: [[1.0, 0.0, 0.0] for _ in texts]
    mock_embed_query.return_value = [1.0, 0.0, 0.0]
    _skill_matching_models(
        mock_with_structured_output,
        SkillMatchAnalysis(
            strengths=["Relevant QA background"], gaps=["No cloud certifications"], summary="A reasonable fit."
        ),
    )

    job = make_job(WORKFLOW)
    job.qualifications = "Experience with QA and Python"
    job.requirements = "Manual and automated testing"
    db_session.flush()
    headers = auth_headers(client, applicant.email)
    application_id = client.post("/applications", json={"requisition_id": job.id}, headers=headers).json()["id"]

    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        client.post(
            f"/applicant/applications/{application_id}/document-upload",
            headers=headers,
            files={"resume_file": ("resume.pdf", f, "application/pdf")},
            data={"resume_data": json.dumps(_RESUME_DATA)},
        )

    resp = client.post(
        f"/applicant/applications/{application_id}/pre-screening",
        headers=headers,
        json={"answers": []},
    )

    assert resp.status_code == 200, resp.text
    # Either advanced past skill_matching (final_decision, per WORKFLOW)
    # or flagged for HR review — both are valid real outcomes depending
    # on the mocked score; either way, no interview_analysis leak.
    assert resp.json()["current_stage"] in ("skill_matching", "final_decision")
    match_payload = next(
        s["payload"] for s in resp.json()["stage_instances"] if s["stage_type"] == "skill_matching"
    )
    assert "interview_analysis" not in match_payload


@patch("app.services.skill_matching.ChatOpenAI.with_structured_output")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_query")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_documents")
def test_hr_profile_survives_legacy_string_shaped_pre_screening_answers(
    mock_embed_documents, mock_embed_query, mock_with_structured_output,
    client, applicant, hr_admin, db_session, make_job, monkeypatch,
):
    """Older applications have skill_matching.payload["answers"] as a
    plain list[str] instead of list[{question_id, value}] -- this used
    to 500 the HR Candidate Profile entirely (TypeError: string indices
    must be integers, not 'str'). Confirmed against real seeded demo
    data (app ids 2 and 263), not synthetic-only. build_candidate_
    profile must degrade gracefully."""
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_embed_documents.side_effect = lambda texts: [[1.0, 0.0, 0.0] for _ in texts]
    mock_embed_query.return_value = [1.0, 0.0, 0.0]
    _skill_matching_models(
        mock_with_structured_output,
        SkillMatchAnalysis(strengths=[], gaps=[], summary="A reasonable fit."),
    )

    job = make_job(WORKFLOW)
    headers = auth_headers(client, applicant.email)
    application_id = client.post("/applications", json={"requisition_id": job.id}, headers=headers).json()["id"]
    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        client.post(
            f"/applicant/applications/{application_id}/document-upload",
            headers=headers,
            files={"resume_file": ("resume.pdf", f, "application/pdf")},
            data={"resume_data": json.dumps(_RESUME_DATA)},
        )
    client.post(
        f"/applicant/applications/{application_id}/pre-screening",
        headers=headers,
        json={"answers": []},
    )

    from app.models.enums import StageType
    from app.models.stage_instance import StageInstance

    instance = db_session.query(StageInstance).filter(
        StageInstance.application_id == application_id,
        StageInstance.stage_type == StageType.skill_matching,
    ).one()
    instance.payload = {**instance.payload, "answers": ["Motivated by the mission.", "Immediately."]}
    db_session.flush()

    hr_headers = auth_headers(client, hr_admin.email)
    profile = client.get(f"/hr/applications/{application_id}/profile", headers=hr_headers)

    assert profile.status_code == 200, profile.text
    qa = profile.json()["pre_screening_qa"]
    assert [e["answer"] for e in qa] == ["Motivated by the mission.", "Immediately."]
    assert all("Legacy submission" in e["question_text"] for e in qa)


def test_onboarding_checklist_rejects_wrong_stage(client, applicant, make_job):
    job = make_job(WORKFLOW)
    headers = auth_headers(client, applicant.email)
    application_id = client.post("/applications", json={"requisition_id": job.id}, headers=headers).json()["id"]

    resp = client.patch(
        f"/applicant/applications/{application_id}/onboarding",
        headers=headers,
        json={"checklist": {"submit_id": True}},
    )

    assert resp.status_code == 409


def test_onboarding_checklist_success(client, applicant, hr_admin, make_job, make_application, make_resume):
    workflow = ["document_upload", "onboarding"]
    job = make_job(workflow)
    application = make_application(job)
    # A resume, because Document Upload will not advance without one
    # (app.domain.stage_requirements.TRANSITION_BLOCKING_KEYS).
    make_resume(application)
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    applicant_headers = auth_headers(client, applicant.email)

    resp = client.post(
        f"/applications/{application.id}/transition",
        json={"target_stage": "onboarding"},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text

    resp = client.patch(
        f"/applicant/applications/{application.id}/onboarding",
        headers=applicant_headers,
        json={"checklist": {"submit_id": True, "sign_contract": False}},
    )

    assert resp.status_code == 200, resp.text
    stage = next(s for s in resp.json()["stage_instances"] if s["stage_type"] == "onboarding")
    assert stage["payload"]["checklist"] == {"submit_id": True, "sign_contract": False}


def test_applicant_never_receives_evaluator_or_hr_internal_payloads(
    client, db_session, applicant, hr_admin, make_job, make_application
):
    """An applicant reading their own application used to receive every
    stage's payload whole -- only skill_matching was redacted. That
    handed them each evaluator's private remarks, ratings, score, tier,
    and user id, plus HR's shortlisting notes and the final decision's
    reasoning and synthesis snapshot. None of it was rendered, so it was invisible
    in the browser and one Network tab away from the candidate being
    written about.

    Written against payloads planted directly on the stage instances, so
    it fails if the allow-list is ever loosened back to a deny-list.
    """
    from app.models.enums import StageType
    from app.models.stage_instance import StageInstance

    job = make_job([
        "document_upload", "shortlisting", "interview_round_1", "final_decision",
    ], title="Redaction Job")
    application = make_application(job)
    db_session.flush()

    planted = {
        StageType.interview_round_1: {
            "schedule": {"date": "2026-09-01", "time": "09:00"},
            "evaluation": {
                "remarks": "Weak on the technical questions; would not hire.",
                "item_ratings": {"A1": 2},
                "computed_score": 2.0,
                "tier": "not_qualified",
                "ai_summary": "Sparse documentation.",
                "submitted_by": 999,
            },
        },
        StageType.shortlisting: {"outcome": "shortlisted", "notes": "Only a lukewarm fit on paper."},
        StageType.final_decision: {
            "decisions": [{"reason": "Stronger candidate available.", "decided_by_name": "Harper"}]
        },
    }
    for stage_type, payload in planted.items():
        instance = db_session.scalars(
            select(StageInstance).where(
                StageInstance.application_id == application.id,
                StageInstance.stage_type == stage_type,
            )
        ).one()
        instance.payload = payload
    db_session.flush()

    headers = auth_headers(client, applicant.email)
    body = client.get(f"/applicant/applications/{application.id}", headers=headers).json()
    by_stage = {s["stage_type"]: (s["payload"] or {}) for s in body["stage_instances"]}

    # The schedule is theirs. The evaluation on the same instance is not.
    assert by_stage["interview_round_1"] == {"schedule": {"date": "2026-09-01", "time": "09:00"}}
    assert by_stage["shortlisting"] == {}
    assert by_stage["final_decision"] == {}

    # Belt and braces: no leaked string survives anywhere in the response.
    serialized = json.dumps(body)
    for secret in ("would not hire", "lukewarm", "Stronger candidate available", "not_qualified"):
        assert secret not in serialized


@patch("app.services.skill_matching.ChatOpenAI.with_structured_output")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_query")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_documents")
def test_pre_screening_no_longer_books_an_exam(
    mock_embed_documents, mock_embed_query, mock_with_structured_output,
    client, applicant, db_session, make_job, monkeypatch,
):
    """The exam pick moved out of Pre-Screening into the Examination
    stage (panel revision list, 15 Oct 2026). A job with open sessions
    asks nothing about them here, and submitting books nothing."""
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_embed_documents.side_effect = lambda texts: [[1.0, 0.0, 0.0] for _ in texts]
    mock_embed_query.return_value = [1.0, 0.0, 0.0]
    _skill_matching_models(
        mock_with_structured_output,
        SkillMatchAnalysis(strengths=["QA background"], gaps=[], summary="A reasonable fit."),
    )

    job = make_job(
        ["document_upload", "skill_matching", "examination", "final_decision"],
        title="Sessions Provisioned",
    )
    job.qualifications = "Experience with QA and Python"
    db_session.add(
        ExamSlot(
            requisition_id=job.id,
            stage_type="examination",
            date="2030-05-01",
            time="09:00",
            end_time="11:30",
            location="Room 2",
            capacity=5,
        )
    )
    db_session.flush()
    headers = auth_headers(client, applicant.email)
    application_id = client.post("/applications", json={"requisition_id": job.id}, headers=headers).json()["id"]
    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        client.post(
            f"/applicant/applications/{application_id}/document-upload",
            headers=headers,
            files={"resume_file": ("resume.pdf", f, "application/pdf")},
            data={"resume_data": json.dumps(_RESUME_DATA)},
        )

    detail = client.get(f"/applicant/applications/{application_id}", headers=headers).json()
    assert detail["current_stage"] == "skill_matching"
    assert detail["exam_sessions"] == []

    resp = client.post(
        f"/applicant/applications/{application_id}/pre-screening",
        headers=headers,
        json={"answers": []},
    )

    # flagged is the other legitimate outcome of a mocked low score
    assert resp.status_code == 200, resp.text
    assert resp.json()["current_stage"] in ("skill_matching", "examination")
    assert db_session.scalars(
        select(ExamSlotBooking).where(ExamSlotBooking.application_id == application_id)
    ).all() == []
