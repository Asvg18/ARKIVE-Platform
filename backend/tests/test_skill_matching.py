"""Tests for the Skill Matching Agent -- chunking, hybrid-retrieval
fusion, and the end-to-end flag/ranking behavior, with LangChain's
OpenAI-touching calls mocked out. No prior coverage existed for this
module."""

import openai
from datetime import date, timedelta
import pytest
from langchain_core.documents import Document
from types import SimpleNamespace
from unittest.mock import patch

from app.models.agent_run import AgentRun
from app.models.application_resume import ApplicationResume
from app.models.enums import RequisitionStatus
from app.models.job_requisition import JobRequisition
from app.schemas.skill_match import AuditVerdict, RequirementCheck, SkillMatchAnalysis
from app.schemas.skill_match import RecheckResult, VerdictAuditResult
from app.services import skill_matching as sm

SIMPLE_WORKFLOW = ["document_upload", "skill_matching", "final_decision"]


class _FakeOpenAIError(openai.OpenAIError):
    """A minimal openai.OpenAIError subclass, so tests don't need to
    reverse-engineer the real constructor signatures of APIError/
    APIConnectionError/etc. just to prove the except clause fires."""


def _fake_analysis(**overrides) -> SkillMatchAnalysis:
    defaults = dict(
        strengths=["Has direct Python/FastAPI experience"],
        gaps=["No cloud certifications listed"],
        summary="A reasonable fit for the role.",
    )
    defaults.update(overrides)
    return SkillMatchAnalysis(**defaults)


def _structured_output_by_schema(
    mock_with_structured_output, *, verdict=None, analysis=None, verdict_audit=None, recheck=None
) -> None:
    """Route each with_structured_output(Schema) call to a stub that
    returns something of that schema's type.

    The qualitative half is two model calls now, not one -- the Scoring
    Agent writes the assessment and the Critic Agent audits it (see
    services/rag_pipeline.py). A single shared return value would hand
    the Critic a SkillMatchAnalysis and ask it for `.is_grounded`, so the
    mock has to dispatch on what was actually requested.

    The default verdict is "grounded": these tests are about ranking,
    flagging and suggestions, so the Critic passing on the first try is
    the path that leaves those assertions measuring what they were
    written to measure.
    """
    results = {
        "SkillMatchAnalysis": analysis if analysis is not None else _fake_analysis(),
        "AuditVerdict": verdict if verdict is not None else AuditVerdict(is_grounded=True),
        "VerdictAuditResult": verdict_audit if verdict_audit is not None else VerdictAuditResult(),
        "RecheckResult": recheck if recheck is not None else RecheckResult(),
    }
    mock_with_structured_output.side_effect = lambda schema, **kw: SimpleNamespace(
        invoke=lambda messages: results[schema.__name__]
    )


# ---------------------------------------------------------------------------
# Pure chunking logic — no DB, no mocking.
# ---------------------------------------------------------------------------


def test_chunk_jd_requirements_splits_and_strips_bullets():
    requisition = JobRequisition(
        title="Backend Engineer",
        department="Engineering",
        qualifications="- Bachelor's degree in CS\n2. 5+ years of Python experience",
        requirements="* Experience with FastAPI\n",
    )
    assert sm._chunk_jd_requirements(requisition) == [
        "Bachelor's degree in CS",
        "5+ years of Python experience",
        "Experience with FastAPI",
    ]


def test_chunk_jd_requirements_leaves_leading_numbers_in_content_alone():
    requisition = JobRequisition(
        title="X", department="Y", qualifications="5+ years of experience", requirements=None
    )
    assert sm._chunk_jd_requirements(requisition) == ["5+ years of experience"]


def test_chunk_jd_requirements_empty_when_no_jd_text():
    requisition = JobRequisition(title="X", department="Y", qualifications=None, requirements=None)
    assert sm._chunk_jd_requirements(requisition) == []


def test_chunk_resume_evidence_covers_all_structured_fields():
    resume = ApplicationResume(
        original_filename="r.pdf",
        stored_path="/tmp/r.pdf",
        experience=[{"title": "Engineer", "company": "Acme", "description": "Built LLM tools"}],
        education=[{"degree": "BS", "field_of_study": "Computer Science", "school": "MSEUF"}],
        skills=["Python", "FastAPI", "SQL", "Docker", "React"],
        certifications=["AWS Certified"],
    )
    chunks = sm._chunk_resume_evidence(resume)
    assert any("Engineer at Acme" in c for c in chunks)
    assert any("BS in Computer Science" in c for c in chunks)
    assert any(c.startswith("Skills:") for c in chunks)
    assert "Certification: AWS Certified" in chunks


def test_chunk_resume_evidence_includes_additional_sections_line_by_line():
    resume = ApplicationResume(
        original_filename="r.pdf",
        stored_path="/tmp/r.pdf",
        experience=[],
        education=[],
        skills=[],
        certifications=[],
        additional_sections=[
            {"title": "Projects", "content": "- Built a Python ETL pipeline\n\n2. Campus event tracker"},
            {"title": "", "content": "Fluent in Filipino and English"},
            {"title": "Awards", "content": "   "},
        ],
    )
    assert sm._chunk_resume_evidence(resume) == [
        "Projects: Built a Python ETL pipeline",
        "Projects: Campus event tracker",
        "Fluent in Filipino and English",
    ]


def test_chunk_resume_evidence_empty_falls_back_to_raw_text():
    resume = ApplicationResume(
        original_filename="r.pdf",
        stored_path="/tmp/r.pdf",
        experience=[],
        education=[],
        skills=[],
        certifications=[],
        raw_extracted_text="Paragraph one.\n\nParagraph two.",
    )
    assert sm._chunk_resume_evidence(resume) == []
    assert sm._fallback_resume_chunks(resume) == ["Paragraph one.", "Paragraph two."]


# ---------------------------------------------------------------------------
# What the match score reads: the reviewed form, not the PDF's text.
# ---------------------------------------------------------------------------


def _reviewed_resume(**overrides) -> ApplicationResume:
    """A form describing a backend engineer, attached to a PDF whose text
    is about coffee -- so any test can tell which of the two was read."""
    defaults = dict(
        original_filename="r.pdf",
        stored_path="/tmp/r.pdf",
        full_name="Juan Dela Cruz",
        email="juan@example.com",
        phone="0917 555 0100",
        location="Lucena City",
        linkedin_url="linkedin.com/in/jdcruz",
        portfolio_url="jdcruz.dev",
        professional_summary="Backend engineer who builds internal tools.",
        experience=[
            {
                "title": "Engineer",
                "company": "Acme",
                "start_date": "2019",
                "end_date": "2023",
                "description": "Built LLM tools",
            }
        ],
        education=[
            {
                "degree": "BS",
                "field_of_study": "Computer Science",
                "school": "MSEUF",
                "start_date": "2015",
                "end_date": "2019",
                "honors": "Cum Laude",
            }
        ],
        skills=["Python", "FastAPI"],
        certifications=["AWS Certified"],
        additional_sections=[{"title": "Projects", "content": "Campus event tracker"}],
        raw_extracted_text="Barista with espresso and latte art experience.",
    )
    defaults.update(overrides)
    return ApplicationResume(**defaults)


def test_scoring_text_is_the_reviewed_form_not_the_pdf_text():
    text = sm._resume_scoring_text(_reviewed_resume())
    assert text.splitlines() == [
        "Backend engineer who builds internal tools.",
        "Engineer at Acme: Built LLM tools",
        "BS in Computer Science, MSEUF, Cum Laude",
        "Skills: Python, FastAPI",
        "Certifications: AWS Certified",
        "Projects: Campus event tracker",
    ]
    assert "espresso" not in text


def test_scoring_text_leaves_out_the_contact_block_and_the_dates():
    text = sm._resume_scoring_text(_reviewed_resume())
    for value in ("Juan", "Dela Cruz", "juan@example.com", "0917", "Lucena", "jdcruz", "2015", "2019", "2023"):
        assert value not in text


def test_scoring_text_skips_blank_entries_instead_of_writing_empty_lines():
    resume = _reviewed_resume(
        professional_summary="  ",
        experience=[
            {"title": "", "company": "", "description": "  "},
            {"title": "Analyst", "company": "", "description": ""},
        ],
        education=[{"degree": "", "field_of_study": "", "school": "", "honors": ""}],
        skills=["Python", " ", ""],
        certifications=[""],
        additional_sections=[{"title": "Awards", "content": "  "}],
    )
    assert sm._resume_scoring_text(resume) == "Analyst\nSkills: Python"


def test_scoring_text_falls_back_to_the_pdf_only_when_the_form_is_blank():
    """The contact block alone is not content, so a form holding nothing
    else falls back too -- the same rule _fallback_resume_chunks applies
    to the analysis."""
    blank = _reviewed_resume(
        professional_summary="",
        experience=[],
        education=[],
        skills=[],
        certifications=[],
        additional_sections=[],
    )
    assert sm._resume_scoring_text(blank) == "Barista with espresso and latte art experience."


def test_resume_embedding_is_computed_from_the_reviewed_form():
    resume = _reviewed_resume()
    embedded: list[list[str]] = []
    embeddings = SimpleNamespace(embed_documents=lambda texts: embedded.append(texts) or [[0.6, 0.8]])

    vector = sm._get_or_compute_resume_embedding(embeddings, resume)

    assert embedded == [[sm._resume_scoring_text(resume)]]
    assert vector == [0.6, 0.8]
    # cached on the row, so a later scoring of this resume reuses it
    assert resume.embedding == [0.6, 0.8]


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion — pure function, no mocking.
# ---------------------------------------------------------------------------


def test_ensemble_rank_fuses_two_rankings():
    a, b, c = Document(page_content="A"), Document(page_content="B"), Document(page_content="C")
    # "B" is 2nd in the BM25 list and 1st in the semantic list — its fused
    # RRF score beats "A" (1st in BM25 only), proving this is a genuine
    # fusion and not just one input passed through.
    fused = sm._ensemble_rank(bm25_docs=[a, b], semantic_docs=[b, c], k=2)
    assert [d.page_content for d in fused] == ["B", "A"]


def test_ensemble_rank_respects_k():
    docs = [Document(page_content=str(i)) for i in range(5)]
    fused = sm._ensemble_rank(docs, docs, k=2)
    assert len(fused) == 2


def test_semantic_score_maps_the_calibration_span_onto_0_to_100():
    assert sm._semantic_score(sm._SEMANTIC_COSINE_FLOOR) == pytest.approx(0.0)
    assert sm._semantic_score(sm._SEMANTIC_COSINE_CEILING) == pytest.approx(100.0)
    midpoint = (sm._SEMANTIC_COSINE_FLOOR + sm._SEMANTIC_COSINE_CEILING) / 2
    assert sm._semantic_score(midpoint) == pytest.approx(50.0)


def test_semantic_score_clamps_outside_the_calibration_span():
    # a negative cosine is possible for embeddings in general, and an
    # identical pair (1.0) sits above the ceiling -- neither may leave 0-100
    assert sm._semantic_score(-0.3) == 0.0
    assert sm._semantic_score(0.1) == 0.0
    assert sm._semantic_score(0.95) == 100.0
    assert sm._semantic_score(1.0) == 100.0


# ---------------------------------------------------------------------------
# The arithmetic half and the verified checks, as pure functions.
# ---------------------------------------------------------------------------


def test_keyword_score_is_bm25_as_a_share_of_the_best_possible():
    units = ["Backend Engineer at Acme: Built APIs with Python and FastAPI", "Skills: Python, FastAPI"]
    scores = sm._keyword_scores_per_requirement(["Python FastAPI", "Espresso latte art"], units)
    assert scores[0] > 50.0
    assert scores[1] == 0.0
    # bounded, whatever the resume's length
    assert all(0.0 <= s <= 100.0 for s in scores)


def test_keyword_score_needs_no_other_job_to_compare_with():
    """The old keyword half was normalised across every open job, so one
    job on its own always scored a neutral 50. This one does not depend
    on what else is posted at all."""
    units = ["Built APIs with Python and FastAPI"]
    alone = sm._keyword_scores_per_requirement(["Experience with Python"], units)
    assert alone[0] > 0.0 and alone[0] != 50.0


def test_coverage_counts_met_partial_and_unverified():
    checks = [
        RequirementCheck(requirement="a", verdict="met", evidence_quote="x", verified=True),
        RequirementCheck(requirement="b", verdict="partial", evidence_quote="y", verified=True),
        RequirementCheck(requirement="c", verdict="met", evidence_quote="invented", verified=False),
        RequirementCheck(requirement="d", verdict="not_met", evidence_quote="", verified=True),
    ]
    assert sm._requirement_coverage(checks) == pytest.approx((1 + 0.5 + 0 + 0) / 4 * 100)


def test_a_quote_that_is_not_in_the_evidence_does_not_count():
    from app.services.rag_pipeline import _verified_checks

    state = {
        "requirements": ["Experience with Python", "Experience with FastAPI", "Teaching experience"],
        "evidence": [
            {"requirement": "Experience with Python", "evidence": ["Built APIs with Python and FastAPI."]},
            {"requirement": "Experience with FastAPI", "evidence": ["Built APIs with Python and FastAPI."]},
            {"requirement": "Teaching experience", "evidence": []},
        ],
    }
    drafts = [
        # verbatim, apart from case and punctuation -- holds
        RequirementCheck(requirement="Experience with Python", verdict="met", evidence_quote="built APIs with Python"),
        # nowhere in the evidence -- does not
        RequirementCheck(
            requirement="Experience with FastAPI", verdict="met", evidence_quote="Led a FastAPI team of ten"
        ),
        # the third requirement was skipped entirely
    ]
    checks = _verified_checks(state, drafts)

    assert [c.requirement for c in checks] == state["requirements"]
    # the skipped one is recorded as a not_met the model never stood behind
    assert [c.verified for c in checks] == [True, False, False]
    assert checks[2].verdict == "not_met"
    assert sm._requirement_coverage(checks) == pytest.approx(100 / 3)


# ---------------------------------------------------------------------------
# End-to-end run_skill_matching — DB fixtures + mocked LangChain calls.
# ---------------------------------------------------------------------------

_REQUIREMENTS = ["Experience with Python", "Experience with FastAPI"]
_QUOTE = "Built APIs with Python and FastAPI"


def _checks(verdict: str) -> list[RequirementCheck]:
    """What the Scoring Agent would return for _setup's two requirements.
    A quote only for the verdicts that need one; `verified` is decided by
    the pipeline, not here."""
    quote = _QUOTE if verdict != "not_met" else ""
    return [RequirementCheck(requirement=r, verdict=verdict, evidence_quote=quote) for r in _REQUIREMENTS]


def _embed_requirements_as(vector):
    """embed_documents stand-in: each requirement line gets `vector`,
    everything else (resume units, chunks, job text) [1, 0, 0] -- which
    is how a test sets the semantic half of the target's score."""
    return lambda texts: [vector if text in _REQUIREMENTS else [1.0, 0.0, 0.0] for text in texts]


def _setup(db_session, make_job, make_application, make_resume, *, title="Backend Engineer"):
    # the dev DB has real seeded job postings outside this test's own
    # transaction -- close them out (rolled back at teardown via the
    # SAVEPOINT fixture, never touches real data permanently) so the
    # suggestions pass only sees jobs this test itself created
    db_session.query(JobRequisition).filter(JobRequisition.status == RequisitionStatus.open).update(
        {JobRequisition.status: RequisitionStatus.closed}
    )
    db_session.flush()

    job = make_job(SIMPLE_WORKFLOW, title=title)
    job.qualifications = _REQUIREMENTS[0]
    job.requirements = _REQUIREMENTS[1]
    application = make_application(job)
    resume = make_resume(
        application,
        experience=[{"title": "Backend Engineer", "company": "Acme", "description": _QUOTE}],
        skills=["Python", "FastAPI"],
        raw_extracted_text="Backend Engineer with Python and FastAPI experience.",
    )
    return job, resume


def _mock_models(mock_embed_documents, mock_embed_query, mock_with_structured_output, *, requirement_vector, verdict, audit=None):
    mock_embed_documents.side_effect = _embed_requirements_as(requirement_vector)
    mock_embed_query.return_value = [1.0, 0.0, 0.0]
    _structured_output_by_schema(
        mock_with_structured_output,
        analysis=_fake_analysis(requirement_checks=_checks(verdict)),
        verdict=audit,
    )


_ALIKE = [1.0, 0.0, 0.0]
_UNLIKE = [0.0, 1.0, 0.0]
_COSINE_066 = [0.66, (1 - 0.66**2) ** 0.5, 0.0]


@patch("app.services.skill_matching.ChatOpenAI.with_structured_output")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_query")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_documents")
def test_a_resume_meeting_every_requirement_scores_high_and_is_not_flagged(
    mock_embed_documents, mock_embed_query, mock_with_structured_output,
    db_session, make_job, make_application, make_resume, monkeypatch,
):
    monkeypatch.setattr(sm.settings, "openai_api_key", "test-key")
    _mock_models(mock_embed_documents, mock_embed_query, mock_with_structured_output, requirement_vector=_ALIKE, verdict="met")
    job, resume = _setup(db_session, make_job, make_application, make_resume)

    result = sm.run_skill_matching(db_session, resume=resume, target_requisition=job)

    assert result.score_method == sm.SCORE_METHOD
    assert result.semantic_score == pytest.approx(100.0)
    assert result.requirement_coverage == pytest.approx(100.0)
    assert result.match_score == pytest.approx(0.5 * result.arithmetic_score + 0.5 * 100.0, abs=0.1)
    assert all(check.verified for check in result.requirement_checks)
    assert result.flagged is False
    assert result.suggested_requisitions == []

    db_session.flush()
    run = db_session.query(AgentRun).filter(AgentRun.application_id == resume.application_id).one()
    assert run.agent_name == "matching_agent"
    assert run.output["match_score"] == result.match_score


@patch("app.services.skill_matching.ChatOpenAI.with_structured_output")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_query")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_documents")
def test_unmet_requirements_pull_a_relevant_resume_below_the_threshold(
    mock_embed_documents, mock_embed_query, mock_with_structured_output,
    db_session, make_job, make_application, make_resume, monkeypatch,
):
    """The case that prompted v2: a resume on the right topic that misses
    the requirements. The arithmetic half alone is high; the verified
    checks say none are met, and that has to show in the score."""
    monkeypatch.setattr(sm.settings, "openai_api_key", "test-key")
    _mock_models(mock_embed_documents, mock_embed_query, mock_with_structured_output, requirement_vector=_ALIKE, verdict="not_met")
    job, resume = _setup(db_session, make_job, make_application, make_resume)

    result = sm.run_skill_matching(db_session, resume=resume, target_requisition=job)

    assert result.arithmetic_score >= sm._FLAG_THRESHOLD
    assert result.requirement_coverage == 0.0
    assert result.match_score == pytest.approx(0.5 * result.arithmetic_score, abs=0.1)
    assert result.flagged is True
    assert result.flag_reason == "below_threshold"


@patch("app.services.skill_matching.ChatOpenAI.with_structured_output")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_query")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_documents")
def test_the_semantic_half_calibrates_each_requirements_best_cosine(
    mock_embed_documents, mock_embed_query, mock_with_structured_output,
    db_session, make_job, make_application, make_resume, monkeypatch,
):
    monkeypatch.setattr(sm.settings, "openai_api_key", "test-key")
    _mock_models(mock_embed_documents, mock_embed_query, mock_with_structured_output, requirement_vector=_COSINE_066, verdict="met")
    job, resume = _setup(db_session, make_job, make_application, make_resume)

    result = sm.run_skill_matching(db_session, resume=resume, target_requisition=job)

    assert result.cosine_similarity == pytest.approx(0.66)
    # above the ceiling, so a full 100 rather than the raw 66
    assert result.semantic_score == pytest.approx(100.0)
    assert result.arithmetic_score == pytest.approx(0.6 * 100.0 + 0.4 * result.keyword_score, abs=0.1)


@patch("app.services.skill_matching.ChatOpenAI.with_structured_output")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_query")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_documents")
def test_other_open_jobs_do_not_change_the_score(
    mock_embed_documents, mock_embed_query, mock_with_structured_output,
    db_session, make_job, make_application, make_resume, monkeypatch,
):
    """The point of v2: the same resume against the same job scores the
    same whatever else is posted. Under v1, opening one related job could
    move it by 40 points."""
    monkeypatch.setattr(sm.settings, "openai_api_key", "test-key")
    _mock_models(mock_embed_documents, mock_embed_query, mock_with_structured_output, requirement_vector=_COSINE_066, verdict="partial")
    job, resume = _setup(db_session, make_job, make_application, make_resume)
    alone = sm.run_skill_matching(db_session, resume=resume, target_requisition=job)

    make_job(SIMPLE_WORKFLOW, title="Senior Backend Engineer", qualifications="Python", requirements="FastAPI, Python")
    make_job(SIMPLE_WORKFLOW, title="Barista", qualifications="Espresso", requirements="Latte art")
    with_others = sm.run_skill_matching(db_session, resume=resume, target_requisition=job)

    assert with_others.match_score == alone.match_score
    assert with_others.keyword_score == alone.keyword_score


@patch("app.services.skill_matching.ChatOpenAI.with_structured_output")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_query")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_documents")
def test_other_openings_are_suggested_only_when_the_score_is_low(
    mock_embed_documents, mock_embed_query, mock_with_structured_output,
    db_session, make_job, make_application, make_resume, monkeypatch,
):
    monkeypatch.setattr(sm.settings, "openai_api_key", "test-key")
    # the target's requirements are unlike the resume, and none is met
    _mock_models(mock_embed_documents, mock_embed_query, mock_with_structured_output, requirement_vector=_UNLIKE, verdict="not_met")
    # the suggestions are a separate whole-resume ranking, in which the
    # resume reads like the Data Analyst posting
    monkeypatch.setattr(sm, "_get_or_compute_resume_embedding", lambda embeddings, resume: [1.0, 0.0, 0.0])
    monkeypatch.setattr(sm, "_get_or_compute_requisition_embedding", lambda embeddings, requisition: [1.0, 0.0, 0.0])
    job, resume = _setup(db_session, make_job, make_application, make_resume, title="Backend Engineer")
    make_job(SIMPLE_WORKFLOW, title="Data Analyst")

    result = sm.run_skill_matching(db_session, resume=resume, target_requisition=job)

    assert result.flagged is True
    assert [m.title for m in result.suggested_requisitions] == ["Data Analyst"]


@patch("app.services.skill_matching.ChatOpenAI.with_structured_output")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_query")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_documents")
def test_only_openings_still_taking_applications_and_not_applied_to_are_suggested(
    mock_embed_documents, mock_embed_query, mock_with_structured_output,
    db_session, make_job, make_application, make_resume, monkeypatch,
):
    """Every opening below reads exactly like the resume; only the one
    the applicant could actually apply to is suggested."""
    monkeypatch.setattr(sm.settings, "openai_api_key", "test-key")
    _mock_models(mock_embed_documents, mock_embed_query, mock_with_structured_output, requirement_vector=_UNLIKE, verdict="not_met")
    monkeypatch.setattr(sm, "_get_or_compute_resume_embedding", lambda embeddings, resume: [1.0, 0.0, 0.0])
    monkeypatch.setattr(sm, "_get_or_compute_requisition_embedding", lambda embeddings, requisition: [1.0, 0.0, 0.0])
    job, resume = _setup(db_session, make_job, make_application, make_resume, title="Backend Engineer")
    make_job(SIMPLE_WORKFLOW, title="Data Analyst")
    make_job(SIMPLE_WORKFLOW, title="Draft Posting").status = RequisitionStatus.draft
    make_job(SIMPLE_WORKFLOW, title="Closed Posting").status = RequisitionStatus.closed
    make_job(SIMPLE_WORKFLOW, title="Past Deadline").application_deadline = date.today() - timedelta(days=1)
    make_application(make_job(SIMPLE_WORKFLOW, title="Already Applied"))
    db_session.flush()

    result = sm.run_skill_matching(db_session, resume=resume, target_requisition=job)

    assert [m.title for m in result.suggested_requisitions] == ["Data Analyst"]


def test_stored_suggestions_drop_jobs_closed_or_applied_to_since(
    db_session, make_job, make_application, applicant
):
    still_open = make_job(SIMPLE_WORKFLOW, title="Still Open")
    closed_since = make_job(SIMPLE_WORKFLOW, title="Closed Since")
    past_deadline = make_job(SIMPLE_WORKFLOW, title="Past Deadline Since")
    applied_since = make_job(SIMPLE_WORKFLOW, title="Applied Since")
    stored = [
        {"requisition_id": j.id, "title": j.title, "department": j.department}
        for j in (still_open, closed_since, past_deadline, applied_since)
    ]
    closed_since.status = RequisitionStatus.closed
    past_deadline.application_deadline = date.today() - timedelta(days=1)
    make_application(applied_since)
    db_session.flush()

    live = sm.live_suggestions(db_session, applicant_id=applicant.id, suggestions=stored)

    assert [s["title"] for s in live] == ["Still Open"]


@patch("app.services.skill_matching.ChatOpenAI.with_structured_output")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_query")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_documents")
def test_the_score_follows_the_form_when_the_pdf_says_otherwise(
    mock_embed_documents, mock_embed_query, mock_with_structured_output,
    db_session, make_job, make_application, make_resume, monkeypatch,
):
    """A form describing a backend engineer, behind a PDF whose text is
    about coffee: the keyword half finds the requirements' words in the
    form, and nothing ever embeds the PDF's text."""
    monkeypatch.setattr(sm.settings, "openai_api_key", "test-key")
    _mock_models(mock_embed_documents, mock_embed_query, mock_with_structured_output, requirement_vector=_ALIKE, verdict="met")
    job, resume = _setup(db_session, make_job, make_application, make_resume)
    resume.raw_extracted_text = "Barista with espresso and latte art experience."
    db_session.flush()

    result = sm.run_skill_matching(db_session, resume=resume, target_requisition=job)

    assert result.keyword_score > 0.0
    assert result.flagged is False
    embedded = [texts for (texts,), _ in mock_embed_documents.call_args_list]
    assert not any(resume.raw_extracted_text in text for texts in embedded for text in texts)


def test_run_skill_matching_raises_when_not_configured(
    db_session, make_job, make_application, make_resume, monkeypatch
):
    monkeypatch.setattr(sm.settings, "openai_api_key", "")
    job, resume = _setup(db_session, make_job, make_application, make_resume)

    with pytest.raises(sm.ExtractionNotConfiguredError):
        sm.run_skill_matching(db_session, resume=resume, target_requisition=job)


@patch("app.services.skill_matching.OpenAIEmbeddings.embed_documents")
def test_run_skill_matching_raises_ai_extraction_failed_on_embedding_error(
    mock_embed_documents, db_session, make_job, make_application, make_resume, monkeypatch
):
    monkeypatch.setattr(sm.settings, "openai_api_key", "test-key")
    mock_embed_documents.side_effect = _FakeOpenAIError("boom")

    job, resume = _setup(db_session, make_job, make_application, make_resume)

    with pytest.raises(sm.AIExtractionFailedError):
        sm.run_skill_matching(db_session, resume=resume, target_requisition=job)


@patch("app.services.skill_matching.ChatOpenAI.with_structured_output")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_query")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_documents")
def test_run_skill_matching_raises_ai_extraction_failed_on_generation_error(
    mock_embed_documents, mock_embed_query, mock_with_structured_output,
    db_session, make_job, make_application, make_resume, monkeypatch,
):
    monkeypatch.setattr(sm.settings, "openai_api_key", "test-key")
    mock_embed_documents.side_effect = _embed_requirements_as(_ALIKE)
    mock_embed_query.return_value = [1.0, 0.0, 0.0]
    mock_with_structured_output.return_value.invoke.side_effect = _FakeOpenAIError("boom")

    job, resume = _setup(db_session, make_job, make_application, make_resume)

    with pytest.raises(sm.AIExtractionFailedError):
        sm.run_skill_matching(db_session, resume=resume, target_requisition=job)


# ---------------------------------------------------------------------------
# Only a score below the threshold flags an application; an unverified
# assessment does not, and its audited checks still count.
# ---------------------------------------------------------------------------


@patch("app.services.skill_matching.ChatOpenAI.with_structured_output")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_query")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_documents")
def test_audited_verdicts_still_count_when_the_prose_is_unverified(
    mock_embed_documents, mock_embed_query, mock_with_structured_output,
    db_session, make_job, make_application, make_resume, monkeypatch,
):
    """A Critic that never signs off the written assessment. The verdicts
    are audited on their own (here the Verdict Auditor agrees with all of
    them), so they still count -- the long-job-description failure, where
    one disputed summary used to throw every verdict away. The prose is
    still unverified, which HR is shown, but a score this good is not
    flagged: flags are for scores below 60 only."""
    monkeypatch.setattr(sm.settings, "openai_api_key", "test-key")
    _mock_models(
        mock_embed_documents, mock_embed_query, mock_with_structured_output,
        requirement_vector=_ALIKE, verdict="met",
        audit=AuditVerdict(is_grounded=False, unsupported_claims=["Has direct Python/FastAPI experience"]),
    )
    job, resume = _setup(db_session, make_job, make_application, make_resume)

    result = sm.run_skill_matching(db_session, resume=resume, target_requisition=job)

    assert result.rag_trace.terminal_state == "manual_review"
    assert result.requirement_coverage == pytest.approx(100.0)
    assert result.match_score == pytest.approx(0.5 * result.arithmetic_score + 50.0, abs=0.1)
    assert result.match_score >= 60
    assert result.flagged is False
    assert result.flag_reason == ""
    # the candidate scored fine -- no "apply elsewhere"
    assert result.suggested_requisitions == []


# ---------------------------------------------------------------------------
# Settling the verdicts: the contradiction check, the Verdict Auditor and
# the re-check (rag_pipeline._settle_verdicts), with a stub model.
# ---------------------------------------------------------------------------

_MASTERS = "Master's degree in Computer Science, Education, or a related field."
_EDUCATION_UNIT = "Master of Education in Computer Science Teaching, [REDACTED]"


def _settle(*, verdict, signal, audit=None, recheck=None):
    from app.services.rag_pipeline import _settle_verdicts

    state = {
        "requirements": [_MASTERS],
        "evidence": [{"requirement": _MASTERS, "evidence": [_EDUCATION_UNIT]}],
        "redacted_chunks": [_EDUCATION_UNIT, "Computer Science Teacher at [REDACTED]: Taught Python"],
        "analysis": _fake_analysis(
            requirement_checks=[
                RequirementCheck(
                    requirement=_MASTERS, verdict=verdict, evidence_quote="" if verdict == "not_met" else _EDUCATION_UNIT
                )
            ]
        ).model_dump(),
    }
    asked: list[str] = []
    results = {
        "VerdictAuditResult": audit if audit is not None else VerdictAuditResult(),
        "RecheckResult": recheck if recheck is not None else RecheckResult(),
    }

    def with_structured_output(schema, **kw):
        asked.append(schema.__name__)
        return SimpleNamespace(invoke=lambda messages: results[schema.__name__])

    llm = SimpleNamespace(with_structured_output=with_structured_output)
    checks, objections, rechecked = _settle_verdicts(state, {"llm": llm}, {_MASTERS: signal})
    return checks[0], objections, rechecked, asked


def test_a_not_met_the_numbers_contradict_is_re_checked_and_corrected():
    """The 2438 case: the resume holds a Master of Education in Computer
    Science Teaching, the first verdict said not_met, and the requirement
    matched that resume line strongly. The re-check reads it again."""
    corrected = RecheckResult(
        requirement_checks=[RequirementCheck(requirement=_MASTERS, verdict="met", evidence_quote="Master of Education in Computer Science Teaching")]
    )
    check, objections, rechecked, asked = _settle(verdict="not_met", signal=90.0, recheck=corrected)

    assert asked == ["VerdictAuditResult", "RecheckResult"]
    assert rechecked == 1 and objections == 0
    assert check.verdict == "met" and check.verified is True
    assert check.note.startswith("Re-checked")


def test_a_not_met_with_weak_evidence_is_read_twice_and_kept_quietly():
    """v3: every not_met gets a routine second reading. One that agrees
    (here the stub re-check answers nothing) leaves the verdict exactly
    as it was -- no note, not disputed."""
    check, _, rechecked, asked = _settle(verdict="not_met", signal=20.0)

    assert asked == ["VerdictAuditResult", "RecheckResult"]
    assert rechecked == 1
    assert check.verdict == "not_met" and check.verified is True and check.note == ""


def test_a_routine_second_reading_that_finds_support_says_so():
    found = RecheckResult(
        requirement_checks=[RequirementCheck(requirement=_MASTERS, verdict="met", evidence_quote="Master of Education in Computer Science Teaching")]
    )
    check, _, _, _ = _settle(verdict="not_met", signal=20.0, recheck=found)

    assert check.verdict == "met" and check.verified is True
    assert check.note.startswith("Re-checked: Judged not met on the first reading")


def test_a_verdict_the_auditor_objects_to_is_re_checked():
    audit = VerdictAuditResult(objections=[{"requirement": _MASTERS, "objection": "The quoted degree is not in Computer Science."}])
    second = RecheckResult(requirement_checks=[RequirementCheck(requirement=_MASTERS, verdict="partial", evidence_quote=_EDUCATION_UNIT)])
    check, objections, rechecked, _ = _settle(verdict="met", signal=20.0, audit=audit, recheck=second)

    assert objections == 1 and rechecked == 1
    assert check.verdict == "partial" and check.verified is True


def test_a_not_met_still_contradicted_after_the_re_check_is_shown_as_disputed():
    still = RecheckResult(requirement_checks=[RequirementCheck(requirement=_MASTERS, verdict="not_met", evidence_quote="")])
    check, _, _, _ = _settle(verdict="not_met", signal=90.0, recheck=still)

    assert check.verdict == "not_met"
    assert check.verified is False
    assert check.note.startswith("Disputed")


def test_a_re_check_that_skips_the_requirement_leaves_it_disputed():
    check, _, _, _ = _settle(verdict="not_met", signal=90.0, recheck=RecheckResult())

    assert check.verified is False
    assert check.note.startswith("Disputed")


def test_the_reading_rule_treats_or_as_alternatives_in_every_judging_prompt():
    from app.services.agents import rag_catalog

    rule = sm._REQUIREMENT_READING_RULE
    assert "alternatives" in rule and "any ONE" in rule
    assert rule in sm._ANALYSIS_SYSTEM_PROMPT
    # the two verdict agents append it at call time
    assert "_REQUIREMENT_READING_RULE" in open(rag_catalog.__file__, encoding="utf-8").read()


@patch("app.services.skill_matching.ChatOpenAI.with_structured_output")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_query")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_documents")
def test_a_low_score_is_flagged_for_fit_even_when_the_critic_is_happy(
    mock_embed_documents, mock_embed_query, mock_with_structured_output,
    db_session, make_job, make_application, make_resume, monkeypatch,
):
    monkeypatch.setattr(sm.settings, "openai_api_key", "test-key")
    _mock_models(mock_embed_documents, mock_embed_query, mock_with_structured_output, requirement_vector=_UNLIKE, verdict="not_met")
    job, resume = _setup(db_session, make_job, make_application, make_resume)

    result = sm.run_skill_matching(db_session, resume=resume, target_requisition=job)

    assert result.match_score < sm._FLAG_THRESHOLD
    assert result.flagged is True
    assert result.flag_reason == "below_threshold"
    assert result.rag_trace.terminal_state == "audit"


# ---------------------------------------------------------------------------
# v3: reading meaning rather than wording, and the rubric HR is shown.
# ---------------------------------------------------------------------------


def test_degree_titles_and_abbreviations_tokenize_alike():
    assert sm._tokenize("Master's degree in Computer Science") == ["master", "degree", "in", "computer", "science"]
    assert sm._tokenize("M.S. in Computer Science")[:2] == ["master", "science"]
    assert sm._tokenize("MS in CS") == ["master", "science", "in", "computer", "science"]
    assert sm._tokenize("BSCS graduate")[:4] == ["bachelor", "science", "computer", "science"]
    assert sm._tokenize("Ph.D. in Physics")[0] == "doctorate"
    # a product name is not a degree
    assert sm._tokenize("MS Office")[0] == "ms"
    # plurals fold, words that merely end in s do not
    assert sm._tokenize("skills systems analysis class") == ["skill", "system", "analysis", "class"]


def test_a_differently_spelled_degree_now_shares_the_keyword_score():
    def keyword(degree_line):
        units = [degree_line, "Skills: Python, Java", "Teacher at School: Taught algorithms"]
        return sm._keyword_scores_per_requirement(["Master's degree in Computer Science"], units)[0]

    # the abbreviation scores as the spelled-out title does (to within
    # its one extra word), better than a different degree in the same
    # field -- and well above the 0 Okapi's idf gave all three
    assert keyword("MS in Computer Science") == pytest.approx(keyword("Masters in Computer Science"), abs=2)
    assert keyword("MS in Computer Science") > keyword("BS in Computer Science") > 0


def test_degree_requirements_are_always_shown_the_education_entries():
    chunks = [
        "Computer Science Teacher at [REDACTED]: Taught Python",
        "Master of Education in Computer Science Teaching, [REDACTED]",
        "Certification: Licensed Professional Teacher",
        "Skills: Python, Java",
    ]
    sections = ["experience", "education", "credential", "skills"]
    retrieved = {
        "Master's degree in Computer Science": [chunks[0]],
        "LET passer or licensed professional teacher": [chunks[0]],
        "Proficient in Python": [chunks[3]],
    }
    completed = sm._ensure_section_evidence(retrieved, chunks, sections)

    # appended after what retrieval found, never in its place
    assert completed["Master's degree in Computer Science"] == [chunks[0], chunks[1]]
    assert completed["LET passer or licensed professional teacher"] == [chunks[0], chunks[2]]
    assert completed["Proficient in Python"] == [chunks[3]]
    # the raw-text fallback has no sections -- left as retrieved
    assert sm._ensure_section_evidence(retrieved, chunks, []) == retrieved


def test_every_evidence_chunk_is_labelled_with_its_section():
    resume = ApplicationResume(
        experience=[{"title": "Teacher", "company": "School", "description": "Taught CS"}],
        education=[{"degree": "Master of Education", "field_of_study": "Computer Science Teaching", "school": "MSEUF"}],
        skills=["Python"],
        certifications=["LET"],
        additional_sections=[
            {"title": "Licenses", "content": "Professional Teacher"},
            {"title": "Awards", "content": "Best Teacher"},
        ],
    )
    labelled = sm._labelled_resume_evidence(resume)
    assert [section for section, _ in labelled] == [
        "experience", "education", "skills", "credential", "credential", "other",
    ]
    assert [text for _, text in labelled] == sm._chunk_resume_evidence(resume)


def test_every_judging_prompt_is_told_how_to_recognise_an_equivalent_qualification():
    rule = sm._REQUIREMENT_READING_RULE
    assert "EQUIVALENT" in rule and "Master of Education major in Computer Science Teaching" in rule
    assert "`basis`" in rule and "`reasoning`" in rule
    assert rule in sm._ANALYSIS_SYSTEM_PROMPT


def test_the_verdict_agents_are_shown_the_role():
    from app.services.agents.rag_catalog import _verdict_block

    requisition = SimpleNamespace(
        title="Computer Science Professor", department="CCS", description="Teach undergraduate computer science courses."
    )
    check = RequirementCheck(
        requirement=_MASTERS, verdict="met", evidence_quote=_EDUCATION_UNIT, basis="equivalent", reasoning="Same field."
    )
    block = _verdict_block([check], {_MASTERS: [_EDUCATION_UNIT]}, role=sm._role_context(requisition))

    assert block.startswith("The role:\nJob Title: Computer Science Professor")
    assert "Teach undergraduate computer science courses." in block
    assert "(basis: equivalent)" in block and "Reasoning given: Same field." in block
    assert sm._role_context(None) == ""


def test_the_degree_rule_reads_level_and_named_field():
    from app.services.rag_pipeline import _degree_finding, _named_fields

    assert _named_fields("Master's degree in Computer Science, Education, or a related field.") == [
        {"computer", "science"},
        {"education"},
    ]
    state = {
        "redacted_chunks": [
            "Computer Science Teacher at [REDACTED]: Taught Python",
            "Master of Education in Computer Science Teaching, [REDACTED]",
        ],
        "chunk_sections": ["experience", "education"],
    }
    held = state["redacted_chunks"][1]
    # the field the requirement names is inside the degree's own field
    assert _degree_finding("Master's degree in Computer Science.", state) == (held, True)
    # and a master's meets a bachelor's requirement
    assert _degree_finding("Bachelor's degree in Computer Science or a related field.", state) == (held, True)
    # any field, when the requirement names none
    assert _degree_finding("Bachelor's degree", state) == (held, True)
    # a field that only shares a word is the model's call
    assert _degree_finding("Master's degree in Computer Engineering", state) == (held, False)
    # not a high enough level, or not the field at all
    assert _degree_finding("PhD in Computer Science", state) is None
    assert _degree_finding("Master's degree in Nursing", state) is None
    assert _degree_finding("Proficient in Python", state) is None


def _degree_settle(requirement, *, first, recheck=None):
    from app.services.rag_pipeline import _settle_verdicts

    state = {
        "requirements": [requirement],
        "evidence": [{"requirement": requirement, "evidence": [_EDUCATION_UNIT]}],
        "redacted_chunks": [_EDUCATION_UNIT],
        "chunk_sections": ["education"],
        "analysis": _fake_analysis(
            requirement_checks=[
                RequirementCheck(
                    requirement=requirement, verdict=first, evidence_quote="" if first == "not_met" else _EDUCATION_UNIT
                )
            ]
        ).model_dump(),
    }
    results = {"VerdictAuditResult": VerdictAuditResult(), "RecheckResult": recheck or RecheckResult()}
    asked: list[str] = []

    def with_structured_output(schema, **kw):
        asked.append(schema.__name__)
        return SimpleNamespace(invoke=lambda messages: results[schema.__name__])

    (check,), _, rechecked = _settle_verdicts(state, {"llm": SimpleNamespace(with_structured_output=with_structured_output)}, {requirement: 40.0})
    return check, rechecked, asked


def test_the_degree_rule_meets_the_professor_case_whatever_the_model_said():
    """The case that prompted v3: "Master's degree in Computer Science"
    against a Master of Education major in Computer Science Teaching,
    which the model read as partly met on one run and met on the next."""
    for first in ("partial", "not_met"):
        check, rechecked, asked = _degree_settle("Master's degree in Computer Science.", first=first)

        assert check.verdict == "met" and check.verified is True and check.basis == "equivalent"
        assert check.evidence_quote == _EDUCATION_UNIT
        assert "Master of Education in Computer Science Teaching" in check.reasoning
        assert check.note.startswith("Met by the degree rule")
        # settled by code, so nothing is sent back to the model
        assert rechecked == 0 and asked == ["VerdictAuditResult"]


def test_the_degree_rule_holds_a_correct_met_against_an_objection():
    """From the eval set: a correct met the Verdict Auditor objected to was
    flipped by the re-check and then marked disputed. The rule now settles
    it whatever the first verdict was."""
    from app.services.rag_pipeline import _settle_verdicts

    requirement = "Master's degree in Computer Science."
    state = {
        "requirements": [requirement],
        "evidence": [{"requirement": requirement, "evidence": [_EDUCATION_UNIT]}],
        "redacted_chunks": [_EDUCATION_UNIT],
        "chunk_sections": ["education"],
        "analysis": _fake_analysis(
            requirement_checks=[RequirementCheck(requirement=requirement, verdict="met", evidence_quote=_EDUCATION_UNIT)]
        ).model_dump(),
    }
    objection = VerdictAuditResult(objections=[{"requirement": requirement, "objection": "Education is not Computer Science."}])
    flipped = RecheckResult(requirement_checks=[RequirementCheck(requirement=requirement, verdict="not_met", evidence_quote="")])
    llm = SimpleNamespace(
        with_structured_output=lambda schema, **kw: SimpleNamespace(
            invoke=lambda messages: {"VerdictAuditResult": objection, "RecheckResult": flipped}[schema.__name__]
        )
    )
    (check,), _, rechecked = _settle_verdicts(state, {"llm": llm}, {requirement: 90.0})

    assert rechecked == 0
    assert check.verdict == "met" and check.verified is True and check.note.startswith("Met by the degree rule")


def test_a_quote_stitched_from_the_evidence_holds_and_an_invented_one_does_not():
    from app.services.rag_pipeline import _normalized, _quote_holds

    evidence = _normalized("Skills: Python, Java, HTML/CSS, JavaScript Skills: SQL, C++, Machine Learning")
    # across two chunks, reordered -- every word is there
    assert _quote_holds(_normalized("Python, Java, and C++"), evidence)
    assert _quote_holds(_normalized("Python, Java, HTML/CSS"), evidence)
    # one word the evidence lacks is enough to fail
    assert not _quote_holds(_normalized("Python, Java, Scala"), evidence)
    assert not _quote_holds(_normalized("Led a FastAPI team"), _normalized("Built APIs with Python and FastAPI."))


def test_a_degree_that_only_overlaps_the_named_field_is_read_again():
    related = RecheckResult(
        requirement_checks=[
            RequirementCheck(requirement="Master's degree in Computer Engineering", verdict="partial", evidence_quote=_EDUCATION_UNIT, basis="related")
        ]
    )
    check, rechecked, asked = _degree_settle("Master's degree in Computer Engineering", first="not_met", recheck=related)

    assert asked == ["VerdictAuditResult", "RecheckResult"] and rechecked == 1
    assert check.verdict == "partial" and check.basis == "related"
    assert "overlaps the one named" in check.note


def test_the_quote_check_keeps_what_the_verdict_rests_on():
    from app.services.rag_pipeline import _verified_checks

    state = {"requirements": [_MASTERS], "evidence": [{"requirement": _MASTERS, "evidence": [_EDUCATION_UNIT]}]}
    draft = RequirementCheck(
        requirement=_MASTERS,
        verdict="met",
        evidence_quote="Master of Education in Computer Science Teaching",
        basis="equivalent",
        reasoning="A master's whose major is Computer Science, for a role teaching it.",
    )
    (check,) = _verified_checks(state, [draft])
    assert check.verified and check.basis == "equivalent" and check.reasoning.startswith("A master's")


@patch("app.services.skill_matching.ChatOpenAI.with_structured_output")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_query")
@patch("app.services.skill_matching.OpenAIEmbeddings.embed_documents")
def test_every_requirement_gets_a_rubric_row_that_adds_up_to_the_score(
    mock_embed_documents, mock_embed_query, mock_with_structured_output,
    db_session, make_job, make_application, make_resume, monkeypatch,
):
    monkeypatch.setattr(sm.settings, "openai_api_key", "test-key")
    _mock_models(mock_embed_documents, mock_embed_query, mock_with_structured_output, requirement_vector=_COSINE_066, verdict="partial")
    job, resume = _setup(db_session, make_job, make_application, make_resume)

    result = sm.run_skill_matching(db_session, resume=resume, target_requisition=job)

    rows = result.requirement_scores
    assert [row.requirement for row in rows] == _REQUIREMENTS
    assert all(row.verdict == "partial" and row.points == 0.5 for row in rows)
    assert all(row.closest_resume_text for row in rows)
    # the rows are the score: their mean similarity is the arithmetic
    # half, their mean points the coverage half
    assert sum(row.similarity_score for row in rows) / len(rows) == pytest.approx(result.arithmetic_score, abs=0.1)
    assert sum(row.points for row in rows) / len(rows) * 100 == pytest.approx(result.requirement_coverage)

    breakdown = sm.read_match_breakdown(result.model_dump())
    assert breakdown.match_score == result.match_score
    assert breakdown.semantic_weight == 0.6 and breakdown.coverage_weight == 0.5
    assert breakdown.requirements == rows


def test_a_v2_score_is_explained_from_its_verdicts_alone():
    payload = {
        "match_score": 64.0,
        "arithmetic_score": 78.0,
        "requirement_coverage": 50.0,
        "score_method": "applied_job_v2",
        "requirement_checks": [
            {"requirement": "Python", "verdict": "met", "evidence_quote": "Python", "verified": True},
            {"requirement": "Java", "verdict": "not_met", "evidence_quote": "", "verified": True},
        ],
    }
    breakdown = sm.read_match_breakdown(payload)
    assert [row.points for row in breakdown.requirements] == [1.0, 0.0]
    assert all(row.similarity_score is None for row in breakdown.requirements)
    # a payload with only a score still explains what it can
    assert sm.read_match_breakdown({"match_score": 71.8}).requirements == []
    assert sm.read_match_breakdown(None) is None


def test_skill_requirements_are_shown_the_whole_skills_list():
    """A skills list split into chunks ("Python, Java" in one, "C++" in the
    next) reads as a list without C++. A skill requirement, or one naming a
    listed skill, is shown the list as one item."""
    chunks = [
        "Computer Science Teacher at [REDACTED]: Taught Python",
        "Skills: Teaching, Python, Java, Curriculum Design",
        "Skills: C++, Educational Technology",
    ]
    sections = ["experience", "skills", "skills"]
    whole = "Skills: Teaching, Python, Java, Curriculum Design, C++, Educational Technology"
    retrieved = {
        "Experience with multiple programming languages such as Python, Java, and C++.": [chunks[1]],
        "Experience with C++": [chunks[0]],
        "Experience with JavaScript": [chunks[0]],
        "Commitment to ongoing professional development": [chunks[0]],
    }
    completed = sm._ensure_section_evidence(retrieved, chunks, sections)

    assert completed["Experience with multiple programming languages such as Python, Java, and C++."] == [
        chunks[1],
        whole,
    ]
    # names a listed skill, though nothing marks it a skills requirement
    assert completed["Experience with C++"] == [chunks[0], whole]
    # "Java" is listed, "JavaScript" is not -- a whole-word match only
    assert completed["Experience with JavaScript"] == [chunks[0]]
    assert completed["Commitment to ongoing professional development"] == [chunks[0]]
