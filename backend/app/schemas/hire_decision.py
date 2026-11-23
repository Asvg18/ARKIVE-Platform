"""Shapes for the hire/reject decision gate (services/hire_decision) and
the permanent record of what HR decided."""

from typing import Literal

from pydantic import BaseModel

# "check_outcome" belongs to the retired reference/background checks.
# Nothing raises it now, but older decision records store it verbatim
# and still have to read back. "shortlisting_outcome" is the same story for
# the Shortlisting stage: outside the WSM, so invisible to the criterion
# walk on its own.
BlockerKey = Literal[
    "stage", "interview_round", "criterion", "check_outcome", "shortlisting_outcome"
]


class DecisionBlocker(BaseModel):
    """One reason this candidate's record isn't complete. Carries a
    human sentence, not a code — rendered verbatim in HR's confirmation
    dialog and stored verbatim in the decision record, so reading an old
    record shows exactly what the decider saw."""

    key: BlockerKey
    label: str
    detail: str


class DecisionReadiness(BaseModel):
    """Whether everything this job's workflow *can* record has been
    recorded. A `not_applicable` criterion (the workflow can never produce
    it) is **not** a blocker, or such jobs could never hire."""

    is_complete: bool
    blockers: list[DecisionBlocker]
    # One plain sentence, reused as the 409's message and the dialog's
    # summary line so the API and the UI can't drift apart.
    summary: str


class DecisionRecordRead(BaseModel):
    """The latest decision record on the final_decision payload
    (reopening and deciding again appends). Headline fields are flattened
    from the stored snapshot; the full snapshot stays in the payload."""

    status: str
    previous_status: str
    reason: str | None
    # True means HR was shown the outstanding items and closed anyway —
    # legitimate, and the single most important field on this record.
    acknowledged_incomplete: bool
    decided_by_name: str | None
    decided_at: str
    # Where the candidate stood in the pipeline at the moment of the
    # decision, which is what makes a premature hire visible after the
    # fact.
    decided_at_stage_label: str | None
    blockers: list[DecisionBlocker]
    final_synthesis_score: float | None
    overall_tier: str | None
