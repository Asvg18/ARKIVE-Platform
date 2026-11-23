"""The Skill Matching Agent's output (services/skill_matching/), and
the shapes its retrieval sub-graph exchanges (services/rag_pipeline.py):
retrieved evidence, the Critic's verdict, and the path taken."""

from typing import Literal

from pydantic import BaseModel, Field


class RequisitionMatch(BaseModel):
    """One requisition's score against a given resume — the same shape
    whether it's the job the candidate applied to or a suggested
    alternative; only which list it ends up in differs."""

    requisition_id: int
    title: str
    department: str
    semantic_score: float
    keyword_score: float
    combined_score: float
    # the raw cosine semantic_score was calibrated from; None on older
    # results
    cosine_similarity: float | None = None


RequirementVerdict = Literal["met", "partial", "not_met"]

#: What a verdict rests on. "direct": the resume says what the
#: requirement asks for. "equivalent": the same qualification under
#: another name, or one whose major or specialisation is the required
#: field (a Master of Education major in Computer Science Teaching, for
#: a role teaching Computer Science). "related": an adjacent field that
#: covers part of it. "transferable": experience that shows it
#: indirectly. "none": nothing in the evidence addresses it.
MatchBasis = Literal["direct", "equivalent", "related", "transferable", "none"]


class RequirementCheck(BaseModel):
    """The Scoring Agent's verdict on one requirement of the applied-to
    job, with the résumé evidence it rests on copied word for word.

    Half of the match score is built from these (see
    skill_matching._requirement_coverage), so the quote is not taken on
    trust: a "met" or "partial" whose quote is not in the evidence
    retrieved for that requirement is counted as "not_met", and
    `verified` says which ones survived that check."""

    requirement: str
    verdict: RequirementVerdict
    evidence_quote: str
    #: defaulted, like `note`, so checks stored before they existed load
    basis: MatchBasis = "none"
    #: one sentence on why the evidence meets the requirement or does
    #: not -- for an "equivalent" basis, why the two are the same thing
    reasoning: str = ""
    #: decided by code (rag_pipeline._verified_checks), which rebuilds
    #: every check -- whatever the model puts here is discarded
    verified: bool = False
    #: set by code when a verdict was sent back for a second look, or
    #: still disputed after one -- shown to HR beside the verdict
    note: str = ""


class RequirementScore(BaseModel):
    """One requirement's whole contribution to match_score, both halves
    side by side -- the row HR reads to see where the number came from.
    Written by code (skill_matching.run_skill_matching), never by a
    model."""

    requirement: str
    #: the arithmetic half for this requirement, each 0-100. None on rows
    #: rebuilt from older payloads that stored verdicts only
    semantic_score: float | None = None
    keyword_score: float | None = None
    similarity_score: float | None = None
    #: the resume line the semantic score was measured against
    closest_resume_text: str = ""
    #: the coverage half: the settled verdict, and the points it earned
    #: (met 1, partial 0.5, not met or unverified 0)
    verdict: RequirementVerdict = "not_met"
    basis: MatchBasis = "none"
    reasoning: str = ""
    evidence_quote: str = ""
    verified: bool = False
    note: str = ""
    points: float = 0.0


class MatchBreakdown(BaseModel):
    """How a stored match_score was arrived at, for HR to read beside it:
    the formula with its weights, both halves' values, and every
    requirement's row. Built on read from the stored payload
    (skill_matching.read_match_breakdown) -- nothing here is recomputed,
    so it explains the number HR sees, not today's version of it."""

    score_method: str
    match_score: float
    #: the arithmetic half and its two parts, all 0-100
    arithmetic_score: float | None
    semantic_score: float | None
    keyword_score: float | None
    #: the verified coverage half, 0-100; None when there were no
    #: verdicts and match_score is the arithmetic half alone
    requirement_coverage: float | None
    #: semantic's share of each requirement's similarity (keyword has
    #: the rest), and coverage's share of match_score (arithmetic has
    #: the rest)
    semantic_weight: float
    coverage_weight: float
    #: points per verdict, e.g. {"met": 1.0, "partial": 0.5, "not_met": 0.0}
    verdict_points: dict[str, float]
    flag_threshold: float
    requirements: list[RequirementScore] = Field(default_factory=list)


class VerdictObjection(BaseModel):
    requirement: str
    objection: str


class VerdictAuditResult(BaseModel):
    """The Verdict Auditor's output: the requirements whose verdict the
    evidence does not bear out, each with why. Empty when it agrees with
    every one -- a correctly cautious verdict is not an objection."""

    objections: list[VerdictObjection] = Field(default_factory=list)


class RecheckResult(BaseModel):
    """The Verdict Re-check Agent's second look at the requirements that
    were disputed -- the same shape as a first verdict, so the same quote
    check applies to it."""

    requirement_checks: list[RequirementCheck] = Field(default_factory=list)


class SkillMatchAnalysis(BaseModel):
    """The qualitative half -- grounded in the actual resume and JD text,
    not a canned template.

    `requirement_checks` is the one part of it that reaches the number:
    the verified share of requirements met is half of match_score
    (skill_matching.run_skill_matching). It is judged per requirement
    against retrieved evidence, audited by the Critic Agent, and every
    quote is checked against that evidence by code before it counts. The
    model never sees the arithmetic half, and never writes a score.

    Defaulted so payloads stored before requirement checks existed still
    load."""

    strengths: list[str]
    gaps: list[str]
    summary: str
    requirement_checks: list[RequirementCheck] = Field(default_factory=list)


class RetrievedEvidence(BaseModel):
    """One JD requirement paired with the resume chunks hybrid retrieval
    actually returned for it. The unit the Scoring Agent reasons over and
    the unit the Critic Agent checks its claims against -- keeping them
    the same object is what lets the Critic say "claim X cites nothing"
    instead of guessing."""

    requirement: str
    evidence: list[str]


class RequirementProbes(BaseModel):
    """One requirement and the search probes written for it.

    `requirement` must come back exactly as it was sent -- it is the join
    key back onto the requirement list, and a model that "helpfully"
    tidies the wording orphans its own probes."""

    requirement: str
    probes: list[str] = Field(default_factory=list)


class QueryExpansion(BaseModel):
    """Every requirement's probes from one model call.

    A wrapper object rather than a bare list because json_schema
    structured output needs an object at the top level -- and because
    doing all requirements in one call is the point: per-requirement
    calls would mean a dozen round trips on a JD with a dozen lines."""

    expansions: list[RequirementProbes] = Field(default_factory=list)


# The Critic's ruling on one strength or gap. The docstring below and the
# field descriptions reach the model through the JSON schema, so the
# reasons for their shape live here instead.
#
# Asked for one by one because a model asked only for a list of
# unsupported claims lists claims its own reasoning accepted. Having to
# name the requirement and say why is what makes a rejection one it
# actually reasoned about.
#
# `accurate`, not `supported`, and after `reason`: `supported` reads as
# "is the requirement supported", so a correct gap gets marked false.
# `claim` is the label the claim was listed under (S1, G3), not its text:
# copying many claims back, the model drifts and pairs a claim with the
# reason meant for another.
class ClaimReview(BaseModel):
    """A ruling on one strength or gap of the assessment."""

    claim: str = Field(description="The label of the strength or gap, as listed: S1, S2, G1, G2, ...")
    requirement: str = Field(default="", description="The requirement whose evidence the claim was checked against.")
    reason: str = Field(default="", description="One sentence: what that evidence shows that makes the claim true or false.")
    accurate: bool = Field(
        description=(
            "True when what the claim says is true of the evidence. For a gap, true when the evidence "
            "really lacks what the gap says is missing."
        )
    )


class AuditVerdict(BaseModel):
    """Critic / Guardrail Agent's structured output. Deliberately not a
    score: the Critic's job is to decide whether the Scoring Agent's
    prose is traceable to retrieved evidence, not to re-judge the
    candidate. A second opinion on fit would just be a second
    hallucination."""

    #: one ruling per strength and gap. When present, `is_grounded` and
    #: `unsupported_claims` are derived from these (rag_catalog.
    #: _settled_verdict), so the verdict cannot disagree with its rulings
    claim_reviews: list[ClaimReview] = Field(default_factory=list)
    #: every claim traces to a retrieved chunk -- the accepting condition
    is_grounded: bool
    #: claims from the analysis with no supporting evidence behind them
    unsupported_claims: list[str] = Field(default_factory=list)
    #: requirements whose retrieval came back too thin to judge; the
    #: Clarify Agent re-queries on exactly these
    needs_more_context: list[str] = Field(default_factory=list)
    #: one line for the execution log, in the Critic's own words
    note: str = ""


class RAGTrace(BaseModel):
    """Which states the retrieval automaton visited, stored with the
    result. `terminal_state` says whether the Critic signed the assessment
    off, which the prose alone cannot show."""

    #: states in visit order, e.g. ["ingestion", "validation", ...]. A
    #: repeat of "scoring" is a clarify retry, so the path shows the
    #: cycle rather than just summarizing it.
    path: list[str] = Field(default_factory=list)
    #: where the automaton stopped: "audit" (clean), "manual_review"
    #: (Critic never satisfied), or "rejected" (nothing to retrieve over)
    terminal_state: str = ""
    #: retries the Clarify Agent spent, 0 when the Critic passed first try
    clarify_loops: int = 0
    #: identifying spans the Compliance Agent removed before any evidence
    #: reached a model -- the blind-screening claim, as a number
    redactions: int = 0
    #: JD requirements retrieval ran against
    requirements_retrieved: int = 0
    #: whether LLM-written probes reached retrieval on this run (not the
    #: same as the setting: expansion can fail and fall back). Stored so
    #: expanded and plain runs can be compared.
    expanded_queries: bool = False
    #: set when the pipeline stopped early, so the UI can explain itself
    degraded_reason: str = ""
    #: verdicts the Verdict Auditor objected to, and how many verdicts
    #: were sent back for a second look (objected, or contradicted by the
    #: evidence score). Measurable after the fact, like expanded_queries.
    verdict_objections: int = 0
    verdicts_rechecked: int = 0


class SkillMatchResult(BaseModel):
    """What is stored on the skill_matching StageInstance.payload; every
    screen reads this stored result rather than recomputing it."""

    # 0.5 x arithmetic_score + 0.5 x requirement_coverage, against the
    # applied-to job (score_method "applied_job_v2"). Older payloads
    # (score_method "") hold a whole-resume cosine + BM25 score.
    match_score: float
    # means over the job's requirements, see run_skill_matching
    semantic_score: float
    keyword_score: float
    # see RequisitionMatch.cosine_similarity; since v2 the mean of each
    # requirement's best cosine against the resume
    cosine_similarity: float | None = None
    # 0.6 x semantic + 0.4 x keyword, per requirement, averaged -- the
    # half no model touches. None on payloads stored before v2
    arithmetic_score: float | None = None
    # verified share of requirements met (met 1, partial 0.5), 0-100.
    # None when there are no checks; match_score is then the arithmetic
    # half alone
    requirement_coverage: float | None = None
    requirement_checks: list["RequirementCheck"] = Field(default_factory=list)
    # one row per requirement with both halves of its score -- the
    # rubric HR is shown beside match_score. Empty before v3
    requirement_scores: list[RequirementScore] = Field(default_factory=list)
    score_method: str = ""
    top_skills: list[str]
    strengths: list[str]
    gaps: list[str]
    summary: str
    flagged: bool
    # Why it was flagged:
    #
    #   "below_threshold"       — match_score < MATCH_FLAG_THRESHOLD,
    #                             the only reason a new match is flagged.
    #   "unverified_assessment" — stored payloads only: older payloads
    #                             may hold it. Nothing writes it now; an
    #                             assessment the Critic Agent never signed
    #                             off is shown to HR as Unverified.
    #   ""                      — not flagged.
    #
    # Defaulted so older payloads still load.
    flag_reason: Literal["below_threshold", "unverified_assessment", ""] = ""
    # Populated only when the score was below threshold -- "you might fit
    # these other openings" is only true of a candidate who scored poorly.
    suggested_requisitions: list[RequisitionMatch]

    # how the qualitative half was arrived at. Optional: this schema is
    # read back from stored JSON, and older payloads lack it
    rag_trace: RAGTrace | None = None

    # the job description version this score was computed against
    # (replacing a description never re-scores anyone). None means
    # version 1.
    jd_version: int | None = None
