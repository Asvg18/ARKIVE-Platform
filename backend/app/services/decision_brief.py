"""The Decision Brief Agent — writes the short justification an HR admin
reads before deciding, from facts insights.py has already computed.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field

import openai
from langchain_openai import ChatOpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infra.config import settings
from app.domain.insights import AgreementRead, AspectScore, match_reading, ordinal
from app.models.agent_run import AgentRun
from app.schemas.decision_brief import DecisionBriefResult
from app.schemas.synthesis import FactRead, FactScore
from app.services.agents import DECISION_BRIEF
from app.services.pdf_text import AIExtractionFailedError, ExtractionNotConfiguredError

__all__ = [
    "AIExtractionFailedError",
    "ExtractionNotConfiguredError",
    "BriefFacts",
    "AGENT_NAME",
    "build_facts",
    "latest_brief",
    "run_decision_brief",
]

_log = logging.getLogger(__name__)

#: convenience alias for queries filtering AgentRun by name -- the agent
#: object itself is still the source of truth
AGENT_NAME = DECISION_BRIEF.name

_SYSTEM_PROMPT = (
    "You are writing a short hiring brief for a university HR "
    "administrator who is about to decide on a candidate. You are given a "
    "list of facts that have already been computed from the candidate's "
    "record — interview rubric averages, whether the evaluators agreed, "
    "the skill match against the job posting, and examination standing.\n\n"
    "Use ONLY those facts. Do not invent experience, credentials, skills, "
    "or opinions that are not in the list. Do not restate the weighting "
    "formula or quote the weights — the administrator can see the "
    "arithmetic elsewhere and does not need it explained.\n\n"
    "`verdict` is ONE short sentence: the overall read, in plain words a "
    "non-technical administrator would use. `rationale` is two to four "
    "sentences saying WHY, naming the specific areas the candidate was "
    "strongest and weakest in and whether the evaluators agreed. Be "
    "direct and concrete. Do not hedge, do not flatter, and do not "
    "recommend a decision the facts do not support — if the record is "
    "mixed, say so plainly."
)


@dataclass(frozen=True)
class BriefFacts:
    """The exact fact list handed to the model, plus its fingerprint.
    `lines` is also shown under the brief; `rows` is the same list for
    layout (empty when rebuilt from stored lines)."""

    lines: list[str]
    fingerprint: str
    rows: list[FactRead] = field(default_factory=list)


def _fingerprint(lines: list[str]) -> str:
    return hashlib.sha256(json.dumps(lines, sort_keys=True).encode()).hexdigest()[:16]


def build_facts(
    *,
    job_title: str,
    match_score: float | None,
    match_gaps: list[str],
    aspects: list[AspectScore],
    agreement: AgreementRead,
    exam_score: float | None,
    exam_rank: int | None,
    exam_cohort: int | None,
) -> BriefFacts:
    """Assembles the fact list. Pure, so the read and write paths produce
    the same fingerprint, which is how a stale brief is detected.

    Each fact is a row whose `text` is the sentence the model sees.
    Changing that wording changes every stored brief's fingerprint."""
    rows: list[FactRead] = [
        FactRead(
            key="position",
            label="Position applied for",
            value=job_title,
            text=f"Position applied for: {job_title}.",
        )
    ]

    if match_score is not None:
        reading = match_reading(match_score)
        rows.append(
            FactRead(
                key="skill_match",
                label="Skill match against the posting",
                value=f"{match_score:g} / 100",
                note=reading,
                text=f"Skill match against the job posting: {match_score:g} out of 100. {reading}",
            )
        )
    if match_gaps:
        rows.append(
            FactRead(
                key="requirement_gaps",
                label="Requirements not evidenced on the resume",
                value=str(len(match_gaps)),
                items=list(match_gaps),
                text=(
                    f"Requirements the resume did not evidence ({len(match_gaps)}): "
                    + " ".join(g.rstrip(".") + "." for g in match_gaps)
                ),
            )
        )

    if aspects:
        ranked = sorted(aspects, key=lambda a: a.mean, reverse=True)
        rows.append(
            FactRead(
                key="rubric",
                label="Rubric averages",
                note="Across every evaluated round, on the form's 1–5 scale.",
                scores=[FactScore(name=a.label, value=a.mean) for a in aspects],
                text=(
                    "Interview rubric averages across every evaluated round, on the form's 1-5 scale: "
                    + "; ".join(f"{a.label} {a.mean:g}" for a in aspects)
                    + "."
                ),
            )
        )
        # only call out a strongest/weakest area when the ratings actually
        # separate them -- if we name one anyway when everything's level,
        # the model *will* elaborate on a distinction the evaluators never
        # made
        if ranked[0].mean > ranked[-1].mean:
            for key, label, aspect in (
                ("strongest_area", "Strongest area", ranked[0]),
                ("weakest_area", "Weakest area", ranked[-1]),
            ):
                rows.append(
                    FactRead(
                        key=key,
                        label=label,
                        value=f"{aspect.label} · {aspect.mean:g} of 5",
                        text=f"{label}: {aspect.label} at {aspect.mean:g} of 5.",
                    )
                )
        else:
            rows.append(
                FactRead(
                    key="rubric_even",
                    label="Spread across areas",
                    note=f"Rated evenly across all {len(aspects)} areas, so no area stands out either way.",
                    text=(
                        f"The candidate was rated evenly across all {len(aspects)} areas of the form "
                        f"— no area stands out either way."
                    ),
                )
            )

    rows.append(
        FactRead(key="agreement", label="Evaluator agreement", note=agreement.summary, text=agreement.summary)
    )

    if exam_score is not None:
        line = f"Examination score: {exam_score:g} out of 100."
        standing = None
        if exam_rank is not None and exam_cohort is not None and exam_cohort > 1:
            standing = f"{ordinal(exam_rank)} of {exam_cohort} candidates who sat it for this job."
            line += f" That places the candidate {standing}"
        rows.append(
            FactRead(key="exam", label="Examination score", value=f"{exam_score:g} / 100", note=standing, text=line)
        )

    lines = [row.text for row in rows]
    return BriefFacts(lines=lines, fingerprint=_fingerprint(lines), rows=rows)


def latest_brief(db: Session, application_id: int) -> dict | None:
    """Most recent brief for this application, or None, read from the
    AgentRun log, where briefs are stored."""
    run = db.scalars(
        select(AgentRun)
        .where(AgentRun.application_id == application_id, AgentRun.agent_name == AGENT_NAME)
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
        .limit(1)
    ).first()
    return run.output if run else None


def run_decision_brief(
    db: Session, *, application_id: int, stage_type: str, facts: BriefFacts
) -> DecisionBriefResult:
    """Writes the Decision Brief and logs it to the AgentRun log, where it
    is cached. Called on write (a scorecard, an exam result), never on
    read, since the Candidate Profile is polled every 8 seconds.

    The model sees only `facts`, the lines shown under the brief: no
    resume, JD or remarks, so every sentence is checkable. The facts'
    fingerprint is stored with the brief, so a brief written before the
    record changed reads as stale. Raises ExtractionNotConfiguredError
    without an OpenAI key, AIExtractionFailedError on a model failure."""
    if not settings.openai_api_key:
        _log.error(
            "The Decision Brief Agent is unavailable: OPENAI_API_KEY is not set. "
            "See backend/.env.example."
        )
        raise ExtractionNotConfiguredError(
            "The written recommendation is temporarily unavailable. Every score and "
            "all the evidence on this page are unaffected. Try again shortly."
        )

    llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.openai_api_key, temperature=0)
    user_content = "Facts about this candidate:\n" + "\n".join(f"- {line}" for line in facts.lines)
    try:
        structured_llm = llm.with_structured_output(DecisionBriefResult, method="json_schema")
        parsed = structured_llm.invoke(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]
        )
    except openai.OpenAIError as exc:
        raise AIExtractionFailedError(
            "The written recommendation could not be generated. Every score and all "
            "the evidence on this page are unaffected. Try again shortly."
        ) from exc

    if parsed is None:
        raise AIExtractionFailedError(
            "The written recommendation could not be generated. Every score and all "
            "the evidence on this page are unaffected. Try again shortly."
        )

    DECISION_BRIEF.log(
        db,
        application_id=application_id,
        triggered_by_stage=stage_type,
        output={**parsed.model_dump(), "fingerprint": facts.fingerprint, "facts": facts.lines},
    )
    return parsed
