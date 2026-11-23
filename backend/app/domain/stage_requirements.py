"""What each stage has to have produced before it counts as done.
domain.dfa says whether a move is legal; this says whether the stage being
left produced its evidence. Pure, and it only reports: callers decide.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.dfa import is_exam_stage, is_interview_stage


class StageRequirementsUnmetError(Exception):
    """The stage being left hasn't produced what it owes.

    Unlike InvalidTransitionError (an illegal move), the move is legal and
    HR can proceed by acknowledging the gap."""

    def __init__(self, *, stage: str, missing: list["MissingRequirement"]):
        self.stage = stage
        self.missing = missing
        super().__init__(f"{stage} is missing: {', '.join(m.label for m in missing)}")


@dataclass(frozen=True)
class MissingRequirement:
    """One thing a stage was supposed to produce and didn't.

    The same shape as DecisionBlocker, so the client renders both with
    one checklist."""

    key: str
    label: str
    detail: str


# Missing requirements that stop a transition (the rest are only
# reported): evidence a person was supposed to record during the stage,
# plus the resume, which every applicant uploads themselves (it needs
# has_resume from the caller). `match_score` never blocks: the agent
# produces it and HR has no way to re-run it.
TRANSITION_BLOCKING_KEYS = frozenset(
    {
        "scorecard",
        "exam_score",
        "decision",
        "resume",
        "shortlisting_outcome",
        # overridable like the rest, for a confirmation given off-system
        "shortlisting_acceptance",
    }
)


def transition_blockers(
    stage_type: str, payload: dict | None, *, has_resume: bool | None = None
) -> list["MissingRequirement"]:
    """The subset of missing_requirements that actually refuses a
    transition.

    `has_resume` must be forwarded, or the resume rule cannot fire."""
    return [
        item
        for item in missing_requirements(stage_type, payload, has_resume=has_resume)
        if item.key in TRANSITION_BLOCKING_KEYS
    ]


def _evaluation_submitted(payload: dict) -> bool:
    """submitted_at, not computed_score: an older-form evaluation has no
    computed_score but was still submitted."""
    evaluation = payload.get("evaluation")
    if not isinstance(evaluation, dict):
        return False
    return evaluation.get("submitted_at") is not None


def missing_requirements(
    stage_type: str,
    payload: dict | None,
    *,
    has_resume: bool | None = None,
) -> list[MissingRequirement]:
    """Everything `stage_type` still owes, given what's recorded.

    Empty means finished; an unknown stage_type also returns empty.
    `has_resume` comes from application_resumes, not the payload; None
    means "didn't look", and the rule is skipped.
    """
    payload = payload or {}

    if stage_type == "document_upload":
        if has_resume is False:
            return [
                MissingRequirement(
                    key="resume",
                    label="Resume",
                    detail="No resume has been uploaded for this application.",
                )
            ]
        return []

    if stage_type == "skill_matching":
        if payload.get("match_score") is None:
            return [
                MissingRequirement(
                    key="match_score",
                    label="Match score",
                    detail="The skill-matching agent has not produced a score for this candidate.",
                )
            ]
        return []

    if stage_type == "shortlisting":
        # a plain yes/no HR records once -- there's nothing to book, just
        # a call to make once the AI Pre-Screening read is in.
        if payload.get("outcome") is None:
            return [
                MissingRequirement(
                    key="shortlisting_outcome",
                    label="Shortlisting decision",
                    detail="HR has not marked this candidate shortlisted or not.",
                )
            ]
        # A shortlisted candidate must confirm before moving on; this fires
        # when HR advances someone who has not answered (overridable, e.g.
        # confirmed by phone). No acceptance block at all (shortlisted
        # before confirmations existed) is not a blocker.
        acceptance = payload.get("acceptance")
        if (
            payload.get("outcome") == "shortlisted"
            and isinstance(acceptance, dict)
            and not acceptance.get("response")
        ):
            return [
                MissingRequirement(
                    key="shortlisting_acceptance",
                    label="Candidate's confirmation",
                    detail="The candidate has not yet confirmed they want to continue.",
                )
            ]
        return []

    if is_exam_stage(stage_type):
        # a schedule is not evidence: booking an exam is not sitting it
        if payload.get("score") is None:
            return [
                MissingRequirement(
                    key="exam_score",
                    label="Examination score",
                    detail="No score has been recorded for this examination.",
                )
            ]
        return []

    if is_interview_stage(stage_type):
        if not _evaluation_submitted(payload):
            return [
                MissingRequirement(
                    key="scorecard",
                    label="Interview scorecard",
                    detail="No evaluator has submitted a scorecard for this round.",
                )
            ]
        return []

    if stage_type == "final_decision":
        if not payload.get("decisions"):
            return [
                MissingRequirement(
                    key="decision",
                    label="Final decision",
                    detail="No hire or reject decision has been recorded.",
                )
            ]
        return []

    # onboarding (terminal) and unknown stages owe nothing
    return []
