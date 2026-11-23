"""Shapes for the Decision Support synthesis: what all the agents
concluded together."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.domain.scorecard import GeneralEvaluationTier
from app.schemas.skill_match import MatchBreakdown

CriterionKey = Literal[
    "skill_match", "exam_percentile", "executive_consensus", "interview_rubric"
]
CriterionStatus = Literal["available", "missing", "not_applicable"]
AgentStatus = Literal["ran", "pending", "not_applicable", "derived"]


class SynthesisCriterion(BaseModel):
    """One of the WSM's four criteria (C1-C4), with the weight it carries
    and whether it's actually available for this candidate."""

    key: CriterionKey
    label: str
    # The institutional weight from thesis 5.1.2.8, p.91 — C1 0.569,
    # C2 0.037, C3 0.043, C4 0.351.
    weight: float
    status: CriterionStatus
    # Normalized 0-100, exactly as fed to compute_final_synthesis_score —
    # so executive_consensus is the 1-5 score already multiplied by 20.
    value: float | None
    # The number in its *original* scale, for display ("3.40 / 5"), since
    # `value`'s normalization is otherwise invisible and confusing.
    display_value: str | None
    # value * weight — this criterion's actual points contributed to the
    # final score. None unless status is "available".
    contribution: float | None
    # One human-readable line: where the number came from, or why it
    # isn't there.
    detail: str


class AgentRunRead(BaseModel):
    """One row of the AgentRun execution log."""

    id: int
    agent_name: str
    label: str
    triggered_by_stage: str
    triggered_by_stage_label: str
    created_at: datetime


class AgentCoverage(BaseModel):
    """Per-agent "did it do its duty on this application" roll-up.

    `kind`: event agents run once and leave an AgentRun row. Decision
    Support is `derived`, recomputed on every read, so it has no run row;
    the criteria list is its answer."""

    agent_name: str
    label: str
    duty: str
    kind: Literal["event", "derived"]
    status: AgentStatus
    run_count: int
    last_run_at: datetime | None


class AspectRead(BaseModel):
    """One HRD-F-APIEF category, averaged across every evaluated round
    (no model involved)."""

    code: str
    label: str
    # The form's own 1-5 item scale, deliberately not rescaled to 0-100:
    # evaluators rate on 1-5 and HR reads the scorecards on 1-5.
    mean: float
    band: str
    rounds_counted: int
    items_rated: int


class RoundRead(BaseModel):
    """One interview round as it reads to HR: who evaluated, what they
    concluded, and whether they broke from the rest of the chain."""

    stage_type: str
    label: str
    evaluator_name: str | None
    evaluator_avatar_url: str | None = None
    score: float | None
    tier: str | None
    tier_label: str | None
    recommendation: str | None
    is_outlier: bool


class AgreementRead(BaseModel):
    submitted_rounds: int
    total_rounds: int
    unanimous: bool
    summary: str
    rounds: list[RoundRead]


class DisputedRequirement(BaseModel):
    """A requirement verdict still disputed after a re-check: the
    requirement in HR's own words, and the note on why, which carries the
    AI's reasoning. Two fields, so the screen can tidy the note for
    display without touching what HR wrote."""

    requirement: str
    note: str


class EvidenceRead(BaseModel):
    """The record from the stages before the interviews, gathered for the
    screen HR reads before deciding."""

    match_score: float | None
    match_reading: str
    match_strengths: list[str]
    match_gaps: list[str]
    # True when the Critic Agent did not sign off the written resume read
    # (rag_trace.terminal_state manual_review/rejected) -- the strengths
    # and gaps above are then shown marked, not as findings
    match_unverified: bool = False
    # requirement verdicts still disputed after a re-check, so HR checks
    # those against the resume instead of trusting them
    match_disputed: list[DisputedRequirement] = []
    # how match_score was arrived at -- the formula, both halves and a
    # row per requirement -- shown to HR beside the score. None when
    # there is no score
    match_breakdown: MatchBreakdown | None = None
    exam_score: float | None
    exam_rank: int | None
    exam_cohort: int | None
    exam_percentile: float | None


class BriefRead(BaseModel):
    """The Decision Brief Agent's cached output.

    `facts` is the exact list the model was given, shown under the brief
    so each sentence can be checked. `stale` is true when the record has
    changed since the brief was written."""

    verdict: str
    rationale: str
    facts: list[str]
    stale: bool


class FactScore(BaseModel):
    name: str
    value: float


class FactRead(BaseModel):
    """One line of the fact sheet, broken out for the screen.

    `text` is the exact sentence the Decision Brief Agent is given (and
    fingerprinted). The other fields are the same fact as data, for
    layout. Both are built from the same values, so they can't disagree."""

    key: Literal[
        "position",
        "skill_match",
        "requirement_gaps",
        "rubric",
        "strongest_area",
        "weakest_area",
        "rubric_even",
        "agreement",
        "exam",
    ]
    label: str
    value: str | None = None
    note: str | None = None
    items: list[str] = []
    scores: list[FactScore] = []
    text: str


class HeadlineSignal(BaseModel):
    """One fact behind the verdict, and which way it points.

    `tone`: supports the verdict (`positive`), routine (`neutral`), or
    wants HR's eye (`attention`), decided here beside the numbers so the
    screen's colour can't drift from the fact. `items` lists what a fact
    counts (e.g. the unaddressed requirements)."""

    key: Literal["evaluators", "exam_rank", "requirement_gaps"]
    label: str
    detail: str
    tone: Literal["positive", "neutral", "attention"]
    items: list[str] = []


class HeadlineRead(BaseModel):
    """The one-line answer, before any arithmetic. `band` is the form's
    own General Evaluation wording; `score` is supporting detail, not
    the headline."""

    band: str | None
    score: float | None
    signals: list[HeadlineSignal]


class CandidateSynthesis(BaseModel):
    """The consolidated view. Attached to CandidateProfile and reused
    verbatim by the Pre-201 package, so a hired candidate's permanent
    record carries the same explanation HR saw before deciding."""

    final_synthesis_score: float | None
    overall_tier: GeneralEvaluationTier | None
    criteria: list[SynthesisCriterion]
    # How many of the four criteria have a value, out of how many this
    # job's workflow could ever produce. criteria_applicable < 4 means
    # final_synthesis_score is structurally unreachable for this job.
    criteria_available: int
    criteria_applicable: int
    criteria_total: int
    # Null exactly when final_synthesis_score is non-null. Otherwise a
    # plain-language sentence naming what's missing and whether it's
    # coming.
    blocked_reason: str | None
    # above: how the score was computed; below: the evidence on the
    # candidate
    headline: HeadlineRead
    brief: BriefRead | None
    # shown under the brief as "Based on" and given to the Decision Brief
    # Agent; built in one place so the stored fingerprint matches it
    fact_sheet: list[str]
    # the same facts, one row per line, broken out for layout -- see
    # FactRead. Describes the *current* record: it matches a brief's own
    # `facts` exactly when that brief isn't stale
    fact_rows: list[FactRead]
    fact_fingerprint: str
    aspects: list[AspectRead]
    agreement: AgreementRead
    evidence: EvidenceRead
    agents: list[AgentCoverage]
    agent_trail: list[AgentRunRead]
