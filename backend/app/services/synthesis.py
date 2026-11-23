"""Builds the Decision Support synthesis (build_synthesis)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.decision_support import (
    EXECUTIVE_CONSENSUS_SCALE,
    W_EVALUATOR_CHAIN,
    W_EXAM,
    W_RUBRIC,
    W_SKILL,
)
from app.domain.dfa import is_exam_stage, is_interview_stage
from app.domain.insights import aspect_scores, evaluator_agreement, match_reading, ordinal
from app.domain.scorecard import TIER_LABELS, GeneralEvaluationTier
from app.models.agent_run import AgentRun
from app.models.job_requisition import JobRequisition
from app.schemas.skill_match import MatchBreakdown
from app.schemas.synthesis import (
    AgentCoverage,
    AgentRunRead,
    AgreementRead,
    AspectRead,
    BriefRead,
    CandidateSynthesis,
    DisputedRequirement,
    EvidenceRead,
    HeadlineRead,
    HeadlineSignal,
    RoundRead,
    SynthesisCriterion,
)
from app.services.agents import AGENTS, BY_NAME
from app.services.decision_brief import build_facts, latest_brief
from app.services.stage_labels import resolve_stage_label

def _fmt(value: float) -> str:
    """Trim a trailing .0 so weights and scores read as people write
    them (85 rather than 85.0, but 84.5 kept)."""
    return f"{value:g}"


def build_synthesis(
    db: Session,
    *,
    application_id: int,
    requisition: JobRequisition,
    match_score: float | None,
    exam_percentile: float | None,
    evaluator_consensus_score: float | None,
    interview_rubric_score: float | None,
    final_synthesis_score: float | None,
    overall_tier: GeneralEvaluationTier | None,
    # defaulted so older callers that only wanted the criteria breakdown
    # keep working unchanged -- every real caller passes these now
    interview_ratings: dict[str, dict] | None = None,
    examinations: dict[str, dict] | None = None,
    match_strengths: list[str] | None = None,
    match_gaps: list[str] | None = None,
    match_unverified: bool = False,
    match_disputed: list[DisputedRequirement] | None = None,
    match_breakdown: MatchBreakdown | None = None,
    exam_rank: int | None = None,
    exam_cohort: int | None = None,
) -> CandidateSynthesis:
    """The Decision Support synthesis for one application: each WSM
    criterion with its weight and contribution, the headline, the facts,
    the stored Decision Brief, and which agents have run (from the
    AgentRun log).

    `final_synthesis_score` is all-or-nothing: a missing input is never
    treated as zero, and each absent criterion says why, `missing` (not
    recorded yet) or `not_applicable` (this workflow can never produce
    it).

    Only reads. The scores come in already computed by
    build_candidate_profile, so the two cannot disagree; the Decision
    Brief is read as stored and marked stale when the facts it was
    written from have changed, never rewritten here."""
    interview_ratings = interview_ratings or {}
    examinations = examinations or {}
    match_strengths = match_strengths or []
    match_gaps = match_gaps or []
    workflow = requisition.workflow_definition or []
    has_skill_matching = "skill_matching" in workflow
    has_exam = any(is_exam_stage(s) for s in workflow)
    has_interview = any(is_interview_stage(s) for s in workflow)

    criteria = _wsm_criteria(
        match_score=match_score,
        exam_percentile=exam_percentile,
        evaluator_consensus_score=evaluator_consensus_score,
        interview_rubric_score=interview_rubric_score,
        has_skill_matching=has_skill_matching,
        has_exam=has_exam,
        has_interview=has_interview,
    )

    available = [c for c in criteria if c.status == "available"]
    applicable = [c for c in criteria if c.status != "not_applicable"]

    runs = list(
        db.scalars(
            select(AgentRun)
            .where(AgentRun.application_id == application_id)
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
        )
    )

    aspects = aspect_scores(interview_ratings)
    agreement = evaluator_agreement(interview_ratings)
    exam_score = _first_recorded_exam_score(examinations)

    facts = build_facts(
        job_title=requisition.title,
        match_score=match_score,
        match_gaps=match_gaps,
        aspects=aspects,
        agreement=agreement,
        exam_score=exam_score,
        exam_rank=exam_rank,
        exam_cohort=exam_cohort,
    )
    # read-only here -- brief gets written when an evaluator submits or
    # HR records an exam result, never on this path (which is on the
    # 8-second live-refresh poll; a model call here would mean an OpenAI
    # request per open tab per 8 seconds)
    stored = latest_brief(db, application_id)

    return CandidateSynthesis(
        final_synthesis_score=final_synthesis_score,
        overall_tier=overall_tier,
        criteria=criteria,
        criteria_available=len(available),
        criteria_applicable=len(applicable),
        criteria_total=len(criteria),
        blocked_reason=_blocked_reason(criteria, final_synthesis_score),
        headline=_headline(
            overall_tier=overall_tier,
            final_synthesis_score=final_synthesis_score,
            agreement=agreement,
            exam_score=exam_score,
            exam_rank=exam_rank,
            exam_cohort=exam_cohort,
            match_gaps=match_gaps,
        ),
        brief=_brief_read(stored, facts),
        fact_sheet=facts.lines,
        fact_rows=facts.rows,
        fact_fingerprint=facts.fingerprint,
        aspects=_aspect_reads(aspects),
        agreement=_agreement_read(agreement),
        evidence=EvidenceRead(
            match_score=match_score,
            match_reading=match_reading(match_score),
            match_strengths=match_strengths,
            match_gaps=match_gaps,
            match_unverified=match_unverified,
            match_disputed=match_disputed or [],
            match_breakdown=match_breakdown,
            exam_score=exam_score,
            exam_rank=exam_rank,
            exam_cohort=exam_cohort,
            exam_percentile=exam_percentile,
        ),
        agents=_agent_coverage(
            runs,
            has_skill_matching=has_skill_matching,
            has_exam=has_exam,
            has_interview=has_interview,
        ),
        agent_trail=_agent_trail(runs, requisition),
    )


def _wsm_criteria(
    *,
    match_score: float | None,
    exam_percentile: float | None,
    evaluator_consensus_score: float | None,
    interview_rubric_score: float | None,
    has_skill_matching: bool,
    has_exam: bool,
    has_interview: bool,
) -> list[SynthesisCriterion]:
    """The Weighted Sum Model's four criteria (C1 skill match, C2 exam
    percentile, C3 executive consensus, C4 interview rubric), each with
    its thesis weight, its value on the 0-100 scale the model uses, and,
    when absent, whether it is still to come or impossible for this
    workflow (_criterion)."""
    return [
        _criterion(
            key="skill_match",
            label="Skill Match",
            weight=W_SKILL,
            raw=match_score,
            applicable=has_skill_matching,
            normalize=lambda v: v,
            display=lambda v: f"{_fmt(v)}%",
            source="Skill Matching Agent, recorded at the pre-screening stage.",
            pending="No skill match recorded yet. The candidate has not completed pre-screening.",
            absent="This job's workflow has no skill matching stage.",
        ),
        _criterion(
            key="exam_percentile",
            label="Examination Percentile",
            weight=W_EXAM,
            raw=exam_percentile,
            applicable=has_exam,
            normalize=lambda v: v,
            display=lambda v: f"{_fmt(v)}th percentile",
            source="Algorithm 03, ranked against every other candidate's score for this requisition.",
            pending="No examination score recorded yet.",
            absent="This job's workflow has no examination stage.",
        ),
        _criterion(
            key="executive_consensus",
            label="Executive Consensus",
            weight=W_EVALUATOR_CHAIN,
            raw=evaluator_consensus_score,
            applicable=has_interview,
            normalize=lambda v: round(v * EXECUTIVE_CONSENSUS_SCALE, 2),
            display=lambda v: f"{v:.2f} / 5",
            source="Algorithm 04 over the interview chain's evaluator scorecards.",
            pending="No interview round has a submitted evaluator scorecard yet.",
            absent="This job's workflow has no interview rounds.",
        ),
        _criterion(
            key="interview_rubric",
            label="Interview Rubric Coverage",
            weight=W_RUBRIC,
            raw=interview_rubric_score,
            applicable=has_interview,
            normalize=lambda v: v,
            display=lambda v: f"{_fmt(v)} / 100",
            source="Interview Synthesis Agent's independent read of each evaluator's documentation.",
            pending="No interview round has been evaluated by the Interview Synthesis Agent yet.",
            absent="This job's workflow has no interview rounds.",
        ),
    ]


def _brief_read(stored: dict | None, facts) -> BriefRead | None:
    """The stored Decision Brief for display, or None when there is none
    usable; `stale` when the facts it was written from have changed."""
    return (
        BriefRead(
            verdict=stored["verdict"],
            rationale=stored["rationale"],
            # facts the brief was actually written from, not today's
            # -- pairing it with a newer fact list would make a
            # stale brief look substantiated
            facts=stored.get("facts") or facts.lines,
            stale=stored.get("fingerprint") != facts.fingerprint,
        )
        # .get on both keys, not a bare truthiness check -- one
        # malformed row from an older shape should degrade to "no
        # brief yet," not 500 the whole Candidate Profile
        if stored and stored.get("verdict") and stored.get("rationale")
        else None
    )


def _aspect_reads(aspects) -> list[AspectRead]:
    """The rubric's four categories, averaged across the submitted rounds."""
    return [
        AspectRead(
            code=a.code,
            label=a.label,
            mean=a.mean,
            band=a.band,
            rounds_counted=a.rounds_counted,
            items_rated=a.items_rated,
        )
        for a in aspects
    ]


def _agreement_read(agreement) -> AgreementRead:
    """Whether the interview rounds agreed, and each round's score."""
    return AgreementRead(
        submitted_rounds=agreement.submitted_rounds,
        total_rounds=agreement.total_rounds,
        unanimous=agreement.unanimous,
        summary=agreement.summary,
        rounds=[
            RoundRead(
                stage_type=r.stage_type,
                label=r.label,
                evaluator_name=r.evaluator_name,
                evaluator_avatar_url=r.evaluator_avatar_url,
                score=r.score,
                tier=r.tier,
                tier_label=r.tier_label,
                recommendation=r.recommendation,
                is_outlier=r.is_outlier,
            )
            for r in agreement.rounds
        ],
    )


def _agent_trail(runs: list[AgentRun], requisition: JobRequisition) -> list[AgentRunRead]:
    """The AgentRun log for this application, newest first."""
    return [
        AgentRunRead(
            id=run.id,
            agent_name=run.agent_name,
            # a run written by a name no longer in the catalog (an
            # agent renamed or removed since) still has to render, so
            # the stored name is its own fallback label
            label=BY_NAME[run.agent_name].label if run.agent_name in BY_NAME else run.agent_name,
            triggered_by_stage=run.triggered_by_stage,
            triggered_by_stage_label=resolve_stage_label(run.triggered_by_stage, requisition),
            created_at=run.created_at,
        )
        for run in runs
    ]


def _first_recorded_exam_score(examinations: dict[str, dict]) -> float | None:
    """The first recorded exam score, for display. The formula uses the
    percentile, averaged across all exam stages."""
    for exam in examinations.values():
        if exam.get("score") is not None:
            return exam["score"]
    return None


def _headline(
    *,
    overall_tier: GeneralEvaluationTier | None,
    final_synthesis_score: float | None,
    agreement: AgreementRead,
    exam_score: float | None,
    exam_rank: int | None,
    exam_cohort: int | None,
    match_gaps: list[str],
) -> HeadlineRead:
    """The band in words first (the form's own wording), the score as
    supporting detail."""
    signals: list[HeadlineSignal] = []

    if agreement.submitted_rounds:
        recommending = sum(
            1
            for r in agreement.rounds
            if r.recommendation in ("highly_recommended", "recommended")
        )
        # only counts rounds that actually carry a recommendation --
        # evaluations from before that field existed aren't back-filled
        # from the tier, so they can't count as a vote either way
        with_recommendation = sum(1 for r in agreement.rounds if r.recommendation)
        if with_recommendation:
            label = f"{recommending} of {with_recommendation} evaluators recommend"
            if recommending == with_recommendation:
                tone = "positive"
            elif recommending * 2 < with_recommendation:
                tone = "attention"
            else:
                tone = "neutral"
        else:
            label = f"{agreement.submitted_rounds} of {agreement.total_rounds} rounds evaluated"
            # a split chain is worth a look; an unfinished one is routine
            if agreement.submitted_rounds > 1 and not agreement.unanimous:
                tone = "attention"
            elif agreement.submitted_rounds == agreement.total_rounds:
                tone = "positive"
            else:
                tone = "neutral"
        signals.append(
            HeadlineSignal(key="evaluators", label=label, detail=agreement.summary, tone=tone)
        )

    if exam_rank is not None and exam_cohort is not None and exam_cohort > 1:
        # where they sit in the cohort: 0 is the top, 1 the bottom -- so a
        # 2nd of 3 reads as middling rather than as good or bad news
        position = (exam_rank - 1) / (exam_cohort - 1)
        if position <= 1 / 3:
            tone = "positive"
        elif position >= 2 / 3:
            tone = "attention"
        else:
            tone = "neutral"
        standing = f"{ordinal(exam_rank)} of the {exam_cohort} candidates who sat this job's examination."
        signals.append(
            HeadlineSignal(
                key="exam_rank",
                label=f"{ordinal(exam_rank)} of {exam_cohort} on the exam",
                detail=f"Scored {_fmt(exam_score)} / 100, {standing}" if exam_score is not None else standing,
                tone=tone,
            )
        )

    if match_gaps:
        signals.append(
            HeadlineSignal(
                key="requirement_gaps",
                label=f"{len(match_gaps)} unaddressed requirement{'' if len(match_gaps) == 1 else 's'}",
                detail="Asked for in the job posting, but not evidenced on the resume.",
                tone="attention",
                items=match_gaps,
            )
        )

    return HeadlineRead(
        band=TIER_LABELS.get(overall_tier) if overall_tier else None,
        score=final_synthesis_score,
        signals=signals,
    )


def _criterion(
    *,
    key,
    label: str,
    weight: float,
    raw: float | None,
    applicable: bool,
    normalize,
    display,
    source: str,
    pending: str,
    absent: str,
) -> SynthesisCriterion:
    """One criterion row. `raw` is the score in its own native scale;
    `normalize` converts it to the 0-100 the WSM consumes (identity for
    three of the four, x20 for the 1-5 executive consensus), and
    `display` renders the native value for a human."""
    if not applicable:
        return SynthesisCriterion(
            key=key,
            label=label,
            weight=weight,
            status="not_applicable",
            value=None,
            display_value=None,
            contribution=None,
            detail=absent,
        )
    if raw is None:
        return SynthesisCriterion(
            key=key,
            label=label,
            weight=weight,
            status="missing",
            value=None,
            display_value=None,
            contribution=None,
            detail=pending,
        )
    value = normalize(raw)
    return SynthesisCriterion(
        key=key,
        label=label,
        weight=weight,
        status="available",
        value=value,
        display_value=display(raw),
        contribution=round(value * weight, 2),
        detail=source,
    )


def _join(names: list[str]) -> str:
    """Oxford-comma list. These strings are read verbatim by HR on the
    Candidate Profile, so a bare ", ".join reading "A, B, so the score…"
    isn't good enough."""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def _blocked_reason(criteria: list[SynthesisCriterion], final: float | None) -> str | None:
    """Plain-language answer to "why is the final score blank?". Splits
    the two cases that matter: data that hasn't arrived yet, versus a
    criterion this workflow can never produce (which makes the WSM final
    score permanently unreachable for the job, not just for now)."""
    if final is not None:
        return None

    impossible = [c for c in criteria if c.status == "not_applicable"]
    pending = [c for c in criteria if c.status == "missing"]

    if impossible:
        names = _join([f"{c.label} ({c.weight:.1%} of the score)" for c in impossible])
        reason = (
            f"This job's workflow cannot produce {names}, so the weighted final "
            f"synthesis score is not reachable for this requisition. The criteria "
            f"that do apply are shown below and remain valid on their own."
        )
        if pending:
            reason += (
                f" Still outstanding among the applicable criteria: "
                f"{_join([c.label for c in pending])}."
            )
        return reason

    return (
        f"Awaiting {_join([c.label for c in pending])}. The final synthesis score is "
        f"computed only once all four criteria are present. A missing input is "
        f"never treated as zero."
    )


def _agent_coverage(
    runs: list[AgentRun], *, has_skill_matching: bool, has_exam: bool, has_interview: bool
) -> list[AgentCoverage]:
    """Which agents were supposed to act on this application, and which
    actually did. An agent whose stage isn't in this job's workflow is
    reported not_applicable rather than pending, so a short workflow
    doesn't read as five agents having failed to run."""
    applicability = {
        "document_parsing_agent": True,
        "matching_agent": has_skill_matching,
        # pre-screening answers are captured on the skill_matching stage,
        # so this agent lives or dies with that stage too
        "interview_analysis_agent": has_skill_matching,
        "exam_scheduling_agent": has_exam,
        "evaluator_scorecard_agent": has_interview,
        "interview_synthesis_agent": has_interview,
        # written once there's something to justify -- in practice, once
        # the interview chain starts. a job with no interview rounds
        # still gets one from match + exam facts alone, so this isn't
        # gated on has_interview
        "decision_brief_agent": True,
        "decision_support_agent": True,
    }

    coverage: list[AgentCoverage] = []
    for agent in AGENTS:
        agent_name, label, duty, kind = agent.name, agent.label, agent.duty, agent.kind
        agent_runs = [r for r in runs if r.agent_name == agent_name]
        if kind == "derived":
            status = "derived"
        elif not applicability[agent_name]:
            status = "not_applicable"
        elif agent_runs:
            status = "ran"
        else:
            status = "pending"
        coverage.append(
            AgentCoverage(
                agent_name=agent_name,
                label=label,
                duty=duty,
                kind=kind,
                status=status,
                run_count=len(agent_runs),
                # max(), not [0] -- runs is sorted newest-first, but this
                # shouldn't silently depend on that ordering
                last_run_at=max((r.created_at for r in agent_runs), default=None),
            )
        )
    return coverage
