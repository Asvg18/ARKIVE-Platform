"""The Interview Synthesis Agent (run_interview_synthesis)."""

import logging

import openai
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from app.infra.config import settings
from app.domain.scorecard import SCORECARD_CATEGORIES
from app.schemas.interview_synthesis import InterviewSynthesisResult
from app.services.agents import INTERVIEW_SYNTHESIS
from app.services.pdf_text import AIExtractionFailedError, ExtractionNotConfiguredError

__all__ = [
    "AIExtractionFailedError",
    "ExtractionNotConfiguredError",
    "run_interview_synthesis",
]

_log = logging.getLogger(__name__)


_ANALYSIS_SYSTEM_PROMPT = (
    "You are a strict, critical HR analyst reviewing one evaluator's "
    "completed interview scorecard for a job candidate. You are given "
    "the rubric's categories and items, each paired with the rating the "
    "evaluator actually gave (1-5, or N/A), plus the evaluator's own "
    "free-text remarks. Judge how thoroughly the evaluator's remarks and "
    "ratings together demonstrate real coverage of each rubric category "
    "— not whether the candidate is good or bad, but whether the "
    "evaluator's own documentation substantiates the ratings given. "
    "`rubric_coverage_score` (0-100) should be low if the remarks are "
    "sparse, generic, or don't address what the ratings claim, and high "
    "if the remarks give concrete, specific evidence across the rated "
    "categories. `summary` is a short (2-4 sentence) critical narrative "
    "of this evaluation's documented thoroughness. Do not invent "
    "claims about the candidate beyond what the evaluator actually wrote."
)


def _rubric_block(item_ratings: dict[str, int | None], remarks: str) -> str:
    lines = []
    for category in SCORECARD_CATEGORIES:
        lines.append(f"{category.code}. {category.label}")
        for item in category.items:
            rating = item_ratings.get(item.code)
            rating_text = "N/A" if rating is None else str(rating)
            lines.append(f"  - {item.label} — rated: {rating_text}")
    rubric_text = "\n".join(lines)
    return f"Rubric and ratings:\n{rubric_text}\n\nEvaluator's remarks:\n{remarks or '(no remarks given)'}"


def run_interview_synthesis(
    db: Session, *, application_id: int, stage_type: str, item_ratings: dict[str, int | None], remarks: str
) -> InterviewSynthesisResult:
    """Reads one evaluator's scorecard (item ratings and remarks) for one
    round and writes a grounded summary with GPT-4o-mini, logged to the
    AgentRun table. Not RAG: the rubric is small, so every category goes to
    the model. rubric_coverage_score is the model's own judgment, not a
    rescale of the evaluator's computed_score (it feeds WSM criterion C4)."""
    if not settings.openai_api_key:
        _log.error(
            "AI Interview Synthesis is unavailable: OPENAI_API_KEY is not set. "
            "See backend/.env.example."
        )
        raise ExtractionNotConfiguredError(
            "The automatic review of this scorecard is temporarily unavailable, so your "
            "evaluation was not submitted. Please try again shortly. If it keeps "
            "happening, contact the HR office."
        )

    llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.openai_api_key, temperature=0)
    user_content = _rubric_block(item_ratings, remarks)
    try:
        structured_llm = llm.with_structured_output(InterviewSynthesisResult, method="json_schema")
        parsed = structured_llm.invoke(
            [
                {"role": "system", "content": _ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]
        )
    except openai.OpenAIError as exc:
        raise AIExtractionFailedError(
            "The automatic review of this scorecard could not be completed, so your "
            "evaluation was not submitted. Please try again shortly. If it keeps "
            "happening, contact the HR office."
        ) from exc

    if parsed is None:
        raise AIExtractionFailedError("The automatic review of this scorecard could not be completed, so your "
            "evaluation was not submitted. Please try again shortly. If it keeps "
            "happening, contact the HR office.")

    INTERVIEW_SYNTHESIS.log(
        db,
        application_id=application_id,
        triggered_by_stage=stage_type,
        output=parsed.model_dump(),
    )
    return parsed
