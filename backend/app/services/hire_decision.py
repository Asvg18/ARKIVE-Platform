"""Decides whether a candidate's record is complete enough to close, and
builds the permanent record of what HR decided."""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.enums import ApplicationStatus
from app.models.job_requisition import JobRequisition
from app.models.user import User
from app.schemas.hire_decision import (
    DecisionBlocker,
    DecisionReadiness,
    DecisionRecordRead,
)
from app.schemas.pipeline import CandidateProfile, StatusUpdateRequest

# these two WSM criteria are derived from the interview chain -- if a
# round's already listed as its own blocker, repeating "Executive
# Consensus is missing" underneath is the same fact one level up, so we
# suppress it explicitly instead of leaving an unexplained special case
_INTERVIEW_DERIVED_CRITERIA = {"executive_consensus", "interview_rubric"}

_FINAL_DECISION = "final_decision"


def build_decision_readiness(
    profile: CandidateProfile, requisition: JobRequisition
) -> DecisionReadiness:
    """Every reason this candidate's record is not yet complete, in the
    order HR would naturally read them: where they are in the pipeline,
    which interview rounds are outstanding, then which scores are absent.
    Reads only the already-built CandidateProfile, so it judges exactly
    what HR is looking at.

    A `not_applicable` criterion is never a blocker — see
    DecisionReadiness' docstring."""
    workflow = list(requisition.workflow_definition or [])
    blockers: list[DecisionBlocker] = []

    # 1. pipeline position -- read positionally off the job's own
    # workflow, never a hardcoded stage name (same lesson executive_
    # triplet had to learn the hard way). no final_decision stage in the
    # workflow means no opinion here, not a wrong one.
    current = profile.current_stage.value if profile.current_stage else None
    if current in workflow and _FINAL_DECISION in workflow:
        remaining = workflow.index(_FINAL_DECISION) - workflow.index(current)
        if remaining > 0:
            blockers.append(
                DecisionBlocker(
                    key="stage",
                    label=f"Still at {profile.current_stage_label or current}",
                    detail=(
                        f"{remaining} more {'stage' if remaining == 1 else 'stages'} "
                        f"before this candidate reaches the final decision point."
                    ),
                )
            )

    # 2. interview rounds with no submitted scorecard. `submitted_at` is
    # the signal, not `computed_score` -- a legacy (older form)
    # evaluation has the former but not the latter, and it was still
    # genuinely submitted.
    interview_blockers = [
        DecisionBlocker(
            key="interview_round",
            label=rating.get("label") or stage_str,
            detail="No evaluator has submitted a scorecard for this round.",
        )
        for stage_str, rating in profile.interview_ratings.items()
        if rating.get("submitted_at") is None
    ]
    blockers.extend(interview_blockers)

    # 2b. Shortlisting sits outside the WSM, so step 3 below (which walks
    # synthesis criteria) never sees it -- a plain HR-recorded outcome
    # with nothing computed from it. Only a recorded outcome closes it.
    for stage_str, shortlist in profile.shortlisting.items():
        if shortlist.get("outcome") is not None:
            continue
        blockers.append(
            DecisionBlocker(
                key="shortlisting_outcome",
                label=shortlist.get("label") or stage_str,
                detail="HR has not marked this candidate shortlisted or not.",
            )
        )

    # 3. missing WSM criteria, minus the ones already spelled out round by
    # round above
    for criterion in profile.synthesis.criteria:
        if criterion.status != "missing":
            continue
        if criterion.key in _INTERVIEW_DERIVED_CRITERIA and interview_blockers:
            continue
        blockers.append(
            DecisionBlocker(key="criterion", label=criterion.label, detail=criterion.detail)
        )

    return DecisionReadiness(
        is_complete=not blockers,
        blockers=blockers,
        summary=_summarize(blockers, profile),
    )


def _summarize(blockers: list[DecisionBlocker], profile: CandidateProfile) -> str:
    if not blockers:
        return "Everything this job's workflow can record has been recorded."
    count = len(blockers)
    noun = "item" if count == 1 else "items"
    return (
        f"{profile.applicant_name}'s record is incomplete: {count} {noun} "
        f"outstanding. Hiring now is allowed, but it will be recorded as a "
        f"decision made on an incomplete record."
    )


def build_decision_record(
    *,
    profile: CandidateProfile,
    readiness: DecisionReadiness,
    body: StatusUpdateRequest,
    actor: User,
    previous_status: ApplicationStatus,
) -> dict:
    """The permanent record written onto the final_decision stage's
    payload. Its synthesis snapshot is frozen, so it always shows what the
    decider saw, not a later recomputation."""
    synthesis = profile.synthesis
    return {
        "status": body.status.value,
        "previous_status": previous_status.value,
        # optional on purpose -- forcing a reason just gets "n/a" typed a
        # thousand times, which is worse than an honest blank
        "reason": (body.reason or "").strip() or None,
        "acknowledged_incomplete": body.acknowledged_incomplete,
        "decided_by": actor.id,
        "decided_by_name": actor.full_name,
        "decided_at": datetime.now(timezone.utc).isoformat(),
        # most useful single field for auditing a premature hire
        "decided_at_stage": profile.current_stage.value if profile.current_stage else None,
        "decided_at_stage_label": profile.current_stage_label,
        "readiness": {
            "is_complete": readiness.is_complete,
            "summary": readiness.summary,
            "blockers": [blocker.model_dump() for blocker in readiness.blockers],
        },
        "synthesis_snapshot": {
            "final_synthesis_score": synthesis.final_synthesis_score,
            # A plain Literal[str], not an Enum — see app.domain.scorecard.
            "overall_tier": synthesis.overall_tier,
            "criteria_available": synthesis.criteria_available,
            "criteria_applicable": synthesis.criteria_applicable,
            "criteria_total": synthesis.criteria_total,
            "blocked_reason": synthesis.blocked_reason,
            "criteria": [
                {
                    "key": criterion.key,
                    "label": criterion.label,
                    "weight": criterion.weight,
                    "status": criterion.status,
                    "value": criterion.value,
                    "display_value": criterion.display_value,
                    "contribution": criterion.contribution,
                }
                for criterion in synthesis.criteria
            ],
        },
    }


def read_decision_record(payload: dict | None) -> DecisionRecordRead | None:
    """Latest decision off a final_decision payload, or None.

    Every field is `.get`-ed: older payloads have no record, which is
    normal, not an error."""
    decisions = (payload or {}).get("decisions") or []
    if not decisions:
        return None
    latest = decisions[-1]
    snapshot = latest.get("synthesis_snapshot") or {}
    readiness = latest.get("readiness") or {}
    return DecisionRecordRead(
        status=latest.get("status", ""),
        previous_status=latest.get("previous_status", ""),
        reason=latest.get("reason"),
        acknowledged_incomplete=bool(latest.get("acknowledged_incomplete")),
        decided_by_name=latest.get("decided_by_name"),
        decided_at=latest.get("decided_at", ""),
        decided_at_stage_label=latest.get("decided_at_stage_label"),
        blockers=[DecisionBlocker(**blocker) for blocker in readiness.get("blockers", [])],
        final_synthesis_score=snapshot.get("final_synthesis_score"),
        overall_tier=snapshot.get("overall_tier"),
    )
