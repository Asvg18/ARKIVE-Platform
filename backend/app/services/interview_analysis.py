"""The Interview Analysis Agent (run_interview_analysis)."""

import logging

import openai
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from app.infra.config import settings
from app.schemas.applicant import PreScreeningAnswer
from app.schemas.interview_analysis import InterviewAnalysisResult
from app.services.agents import INTERVIEW_ANALYSIS
from app.services.pdf_text import AIExtractionFailedError, ExtractionNotConfiguredError

__all__ = [
    "AIExtractionFailedError",
    "ExtractionNotConfiguredError",
    "run_interview_analysis",
]

_log = logging.getLogger(__name__)


_ANALYSIS_SYSTEM_PROMPT = (
    "You are a strict, critical HR analyst reviewing an applicant's "
    "written answers to a job's AI Pre-Screening questions. You are given "
    "each question paired with the applicant's own answer, or a note that "
    "no answer was given. Evaluate honestly and specifically — do not "
    "default to encouraging language. `strengths` must be concrete points "
    "genuinely supported by what the applicant actually wrote. `gaps` "
    "must be concrete weaknesses: missing answers, vague or evasive "
    "responses, or answers that don't address the question asked. "
    "`summary` is a short (2-4 sentence) critical narrative of overall "
    "impression from these answers alone. Do not invent claims the "
    "applicant did not make."
)


def _qa_block(questions: list[dict], answers: list[PreScreeningAnswer]) -> str:
    answers_by_id = {a.question_id: a.value for a in answers if a.value.strip()}
    return "\n".join(
        f"- Q: {q['text']}\n  A: {answers_by_id.get(q['id'], '(no answer provided)')}"
        for q in questions
    )


def run_interview_analysis(
    db: Session, *, application_id: int, questions: list[dict], answers: list[PreScreeningAnswer]
) -> InterviewAnalysisResult:
    """Reads the applicant's pre-screening answers and writes a grounded
    analysis with GPT-4o-mini, logged to the AgentRun table. Not RAG: the
    answers are a few short pairs, so every question goes to the model
    with its answer (or "no answer provided"). Raises
    ExtractionNotConfiguredError without an OpenAI key,
    AIExtractionFailedError on a model failure."""
    if not settings.openai_api_key:
        _log.error(
            "AI Interview Analysis is unavailable: OPENAI_API_KEY is not set. "
            "See backend/.env.example."
        )
        raise ExtractionNotConfiguredError(
            "Pre-screening is temporarily unavailable, so your answers were not "
            "submitted. Please try again shortly. If it keeps happening, contact "
            "the HR office."
        )

    llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.openai_api_key, temperature=0)
    user_content = (
        "Pre-screening questions and the applicant's answers, in order:\n" + _qa_block(questions, answers)
    )
    try:
        structured_llm = llm.with_structured_output(InterviewAnalysisResult, method="json_schema")
        parsed = structured_llm.invoke(
            [
                {"role": "system", "content": _ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]
        )
    except openai.OpenAIError as exc:
        raise AIExtractionFailedError(
            "Pre-screening could not be completed, so your answers were not "
            "submitted. Please try again shortly. If it keeps happening, contact "
            "the HR office."
        ) from exc

    if parsed is None:
        raise AIExtractionFailedError("Pre-screening could not be completed, so your answers were not "
            "submitted. Please try again shortly. If it keeps happening, contact "
            "the HR office.")

    INTERVIEW_ANALYSIS.log(
        db,
        application_id=application_id,
        triggered_by_stage="skill_matching",
        output=parsed.model_dump(),
    )
    return parsed
