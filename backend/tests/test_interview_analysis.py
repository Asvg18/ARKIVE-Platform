"""Tests for the Interview Analysis Agent -- grounded GPT-4o-mini
analysis of an applicant's AI Pre-Screening answers, with the
OpenAI-touching call mocked out, plus the question-id-to-text join on
the HR Candidate Profile. No prior coverage existed for either."""

import openai
import pytest
from unittest.mock import patch

from app.models.agent_run import AgentRun
from app.models.enums import StageType
from app.models.stage_instance import StageInstance
from app.schemas.applicant import PreScreeningAnswer
from app.schemas.interview_analysis import InterviewAnalysisResult
from app.services import interview_analysis as ia
from tests.conftest import auth_headers

WORKFLOW = ["document_upload", "skill_matching", "final_decision"]

_QUESTIONS = [
    {"id": "q1", "text": "Why do you want this job?", "required": True},
    {"id": "q2", "text": "Describe a challenge you overcame.", "required": False},
]


class _FakeOpenAIError(openai.OpenAIError):
    """A minimal openai.OpenAIError subclass, so tests don't need to
    reverse-engineer the real constructor signatures of APIError/
    APIConnectionError/etc. just to prove the except clause fires."""


def _fake_result(**overrides) -> InterviewAnalysisResult:
    defaults = dict(
        strengths=["Clearly explains motivation for the role"],
        gaps=["Second question left unanswered"],
        summary="A mixed impression — strong on motivation, thin on evidence.",
    )
    defaults.update(overrides)
    return InterviewAnalysisResult(**defaults)


# ---------------------------------------------------------------------------
# run_interview_analysis — DB fixtures + mocked LangChain call.
# ---------------------------------------------------------------------------


@patch("app.services.interview_analysis.ChatOpenAI.with_structured_output")
def test_run_interview_analysis_success_logs_agent_run(
    mock_with_structured_output, db_session, make_job, make_application, monkeypatch
):
    monkeypatch.setattr(ia.settings, "openai_api_key", "test-key")
    mock_with_structured_output.return_value.invoke.return_value = _fake_result()

    job = make_job(WORKFLOW)
    application = make_application(job)
    answers = [PreScreeningAnswer(question_id="q1", value="I want to grow my backend skills here.")]

    result = ia.run_interview_analysis(
        db_session, application_id=application.id, questions=_QUESTIONS, answers=answers
    )

    assert result.strengths == ["Clearly explains motivation for the role"]
    assert result.summary.startswith("A mixed impression")

    db_session.flush()
    run = db_session.query(AgentRun).filter(AgentRun.application_id == application.id).one()
    assert run.agent_name == "interview_analysis_agent"
    assert run.triggered_by_stage == "skill_matching"
    assert run.output["summary"] == result.summary


@patch("app.services.interview_analysis.ChatOpenAI.with_structured_output")
def test_run_interview_analysis_marks_unanswered_questions(
    mock_with_structured_output, db_session, make_job, make_application, monkeypatch
):
    monkeypatch.setattr(ia.settings, "openai_api_key", "test-key")
    mock_with_structured_output.return_value.invoke.return_value = _fake_result()

    job = make_job(WORKFLOW)
    application = make_application(job)
    # q1 answered, q2 left out entirely — both should still show up in the
    # prompt sent to the model, q2 with the explicit "no answer" marker.
    answers = [PreScreeningAnswer(question_id="q1", value="I want to grow my backend skills here.")]

    ia.run_interview_analysis(db_session, application_id=application.id, questions=_QUESTIONS, answers=answers)

    sent_messages = mock_with_structured_output.return_value.invoke.call_args[0][0]
    user_content = sent_messages[1]["content"]
    assert "I want to grow my backend skills here." in user_content
    assert "Describe a challenge you overcame." in user_content
    assert "(no answer provided)" in user_content


def test_run_interview_analysis_raises_when_not_configured(
    db_session, make_job, make_application, monkeypatch
):
    monkeypatch.setattr(ia.settings, "openai_api_key", "")
    job = make_job(WORKFLOW)
    application = make_application(job)

    with pytest.raises(ia.ExtractionNotConfiguredError):
        ia.run_interview_analysis(db_session, application_id=application.id, questions=_QUESTIONS, answers=[])


@patch("app.services.interview_analysis.ChatOpenAI.with_structured_output")
def test_run_interview_analysis_raises_ai_extraction_failed_on_generation_error(
    mock_with_structured_output, db_session, make_job, make_application, monkeypatch
):
    monkeypatch.setattr(ia.settings, "openai_api_key", "test-key")
    mock_with_structured_output.return_value.invoke.side_effect = _FakeOpenAIError("boom")

    job = make_job(WORKFLOW)
    application = make_application(job)

    with pytest.raises(ia.AIExtractionFailedError):
        ia.run_interview_analysis(db_session, application_id=application.id, questions=_QUESTIONS, answers=[])


# ---------------------------------------------------------------------------
# HR Candidate Profile — question-id-to-text join, never covered before.
# ---------------------------------------------------------------------------


def test_candidate_profile_joins_pre_screening_qa_and_interview_analysis(
    client, db_session, make_job, make_application, make_resume, hr_admin
):
    job = make_job(WORKFLOW)
    job.pre_screening_questions = _QUESTIONS
    application = make_application(job)
    # A resume, because Document Upload will not advance without one
    # (app.domain.stage_requirements.TRANSITION_BLOCKING_KEYS).
    make_resume(application)
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        f"/applications/{application.id}/transition",
        json={"target_stage": "skill_matching"},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text

    instance = db_session.query(StageInstance).filter(
        StageInstance.application_id == application.id,
        StageInstance.stage_type == StageType.skill_matching,
    ).one()
    instance.payload = {
        "answers": [
            {"question_id": "q1", "value": "I want to grow my backend skills here."},
            # q-deleted: HR removed this question after the candidate answered it.
            {"question_id": "q-deleted", "value": "An answer to a question that no longer exists."},
        ],
        "interview_analysis": {
            "strengths": ["Clearly explains motivation for the role"],
            "gaps": ["Second question left unanswered"],
            "summary": "A mixed impression.",
        },
    }
    db_session.commit()

    profile = client.get(f"/hr/applications/{application.id}/profile", headers=hr_headers).json()

    qa_by_id = {entry["question_id"]: entry for entry in profile["pre_screening_qa"]}
    assert qa_by_id["q1"]["question_text"] == "Why do you want this job?"
    assert qa_by_id["q1"]["answer"] == "I want to grow my backend skills here."
    # Deleted question falls back to the raw id rather than erroring.
    assert qa_by_id["q-deleted"]["question_text"] == "q-deleted"

    assert profile["interview_analysis_summary"] == "A mixed impression."
    assert profile["interview_analysis_strengths"] == ["Clearly explains motivation for the role"]
    assert profile["interview_analysis_gaps"] == ["Second question left unanswered"]
