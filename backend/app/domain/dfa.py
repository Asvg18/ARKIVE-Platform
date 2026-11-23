"""The hiring-stage DFA, generated per job from its workflow. Pure; what a
stage must have produced is domain/stage_requirements.
"""

from __future__ import annotations


class InvalidTransitionError(Exception):
    """Raised when a requested transition isn't the immediate next stage
    in the job's workflow_definition. Carries enough detail for the caller
    to build a clear 422 response."""

    def __init__(
        self,
        *,
        current_stage: str | None,
        target_stage: str,
        reason: str,
        expected_stage: str | None = None,
    ):
        self.current_stage = current_stage
        self.target_stage = target_stage
        # the stage to move to instead, as a raw key the caller can label;
        # None when there is none
        self.expected_stage = expected_stage
        self.reason = reason
        super().__init__(reason)


def is_interview_stage(stage_type: str) -> bool:
    """True for both the legacy fixed slots (interview_hr_director/
    dept_head/vp) and the generic interview_round_1..6 slots — all share
    this prefix by construction, so this needs no update as the slot
    count changes."""
    return stage_type.startswith("interview_")


def is_exam_stage(stage_type: str) -> bool:
    """True for the legacy singular `examination` slot and the generic
    examination_1..4 slots. No trailing underscore in the prefix (unlike
    is_interview_stage's "interview_") — the legacy value has no _k
    suffix, so a bare "examination" prefix covers both in one check."""
    return stage_type.startswith("examination")


def build_transition_table(workflow_definition: list[str]) -> dict[str, str | None]:
    """stage -> its one legal next stage, in the job's own order; None for
    the last stage."""
    table: dict[str, str | None] = {}
    for i, stage in enumerate(workflow_definition):
        table[stage] = workflow_definition[i + 1] if i + 1 < len(workflow_definition) else None
    return table


def validate_transition(
    workflow_definition: list[str],
    current_stage: str | None,
    target_stage: str,
) -> None:
    """Raises InvalidTransitionError unless `target_stage` is the immediate
    next stage (the first stage when there is no current one). Forward
    only, one step at a time."""
    if target_stage not in workflow_definition:
        raise InvalidTransitionError(
            current_stage=current_stage,
            target_stage=target_stage,
            reason=f"'{target_stage}' is not a stage in this job's workflow",
        )

    if current_stage is None:
        expected = workflow_definition[0]
    else:
        if current_stage not in workflow_definition:
            raise InvalidTransitionError(
                current_stage=current_stage,
                target_stage=target_stage,
                reason=f"'{current_stage}' is not a stage in this job's workflow",
            )
        expected = build_transition_table(workflow_definition)[current_stage]

    if expected is None:
        raise InvalidTransitionError(
            current_stage=current_stage,
            target_stage=target_stage,
            reason=f"'{current_stage}' is the terminal stage; there is no valid next stage",
        )

    if target_stage != expected:
        raise InvalidTransitionError(
            current_stage=current_stage,
            target_stage=target_stage,
            expected_stage=expected,
            reason=(
                f"Invalid transition: from '{current_stage}', the only valid "
                f"next stage is '{expected}', not '{target_stage}'"
            ),
        )
