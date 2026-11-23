"""Job openings: the dashboard summary, creating and opening or closing a
job, its pre-screening questions, its workflow, and the job read models.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.dfa import is_interview_stage
from app.domain.interview_slots import ALLOWED_DURATIONS
from app.models.enums import RequisitionStatus, StageType
from app.schemas.job_description import JobDescriptionSection


class RequisitionSummary(BaseModel):
    id: int
    title: str
    department: str
    active_candidate_count: int


class DashboardSummary(BaseModel):
    """Backs the HR Command Center's stat tiles -- all real counts from
    the DB, nothing stubbed."""

    open_requisitions: int
    active_candidates: int
    pending_final_approvals: int
    # None until at least one application has been marked hired — avoids
    # reporting a misleading 0-day average from an empty sample.
    avg_time_to_hire_days: float | None
    requisitions: list[RequisitionSummary]


def _check_durations(durations: dict[str, int] | None) -> dict[str, int] | None:
    """Interview lengths only for interview rounds, and only the lengths
    HR can pick (domain.interview_slots.ALLOWED_DURATIONS)."""
    if durations is None:
        return None
    for stage, minutes in durations.items():
        if not is_interview_stage(stage):
            raise ValueError("Interview lengths can only be set for interview rounds.")
        if minutes not in ALLOWED_DURATIONS:
            allowed = ", ".join(str(m) for m in ALLOWED_DURATIONS)
            raise ValueError(f"An interview can be {allowed} minutes long.")
    return durations


class RequisitionCreateRequest(BaseModel):
    """Job Opening Builder submission. publish=False keeps the
    requisition a draft, invisible on /public/jobs.

    The builder sends `workflow_definition` (+ round/exam labels) and
    `pre_screening_questions`; without a workflow_definition,
    `workflow_preset` picks a built-in shape. Publishing is refused unless
    the job is complete (app.domain.publish_rules); application_deadline
    is required to publish, optional for a draft. The text fields arrive
    as HR reviewed them, whether typed or read from a JD PDF."""

    title: str = Field(min_length=1, max_length=255)
    department: str = Field(min_length=1, max_length=255)
    description: str | None = None
    qualifications: str | None = None
    requirements: str | None = None
    additional_sections: list[JobDescriptionSection] = Field(default_factory=list, max_length=30)
    jd_filename: str | None = None
    # the id POST /hr/requisitions/extract-jd returned for the PDF it read,
    # so version 1 of this job keeps the actual document. None when HR
    # typed the details by hand.
    jd_upload_id: str | None = None
    application_deadline: date | None = None
    workflow_preset: Literal["standard", "streamlined"] = "standard"
    workflow_definition: list[StageType] | None = Field(default=None, min_length=1)
    interview_round_labels: dict[str, str] | None = None
    examination_labels: dict[str, str] | None = None
    # minutes per interview round -- see JobRequisition.interview_durations
    interview_durations: dict[str, int] | None = None
    pre_screening_questions: list["PreScreeningQuestion"] = Field(default_factory=list)
    publish: bool = True

    @field_validator("interview_durations")
    @classmethod
    def durations_are_allowed(cls, durations: dict[str, int] | None) -> dict[str, int] | None:
        return _check_durations(durations)

    @field_validator("workflow_definition")
    @classmethod
    def stages_must_be_unique(cls, stages: list[StageType] | None) -> list[StageType] | None:
        # same rule as WorkflowUpdateRequest: a repeated stage corrupts
        # the DFA's transition table
        if stages is not None and len(set(stages)) != len(stages):
            raise ValueError("Each stage may only appear once in a workflow.")
        return stages

    @model_validator(mode="after")
    def deadline_required_to_publish(self) -> "RequisitionCreateRequest":
        if self.publish and self.application_deadline is None:
            raise ValueError("application_deadline is required to publish a job opening.")
        return self


class RequisitionStatusUpdateRequest(BaseModel):
    """Take a posting down, put one back up, or publish a draft.

    `draft` is not a reachable target: a live posting sent back to draft
    would vanish from HR's lists. Closing is the reversible way down.

    `application_deadline` is read only when opening: a reopened job
    whose deadline has passed would still be missing from /public/jobs,
    so the new date comes in the same request.
    """

    status: RequisitionStatus
    application_deadline: date | None = None

    @field_validator("status")
    @classmethod
    def status_must_not_be_draft(cls, status: RequisitionStatus) -> RequisitionStatus:
        if status is RequisitionStatus.draft:
            raise ValueError(
                "A published job opening cannot be returned to draft. Close it instead: "
                "closing hides it from applicants and can be undone."
            )
        return status


class PreScreeningQuestion(BaseModel):
    """One HR-authored pre-screening question. `id` is stable, so saved
    answers stay matched to their question when questions are edited,
    reordered, added or removed."""

    id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=500)
    required: bool = True


class PreScreeningQuestionsUpdateRequest(BaseModel):
    questions: list[PreScreeningQuestion]


class RequisitionListItem(BaseModel):
    """One row of GET /hr/requisitions: every job opening whatever its
    status (the only list with drafts and closed postings)."""

    id: int
    title: str
    department: str
    status: RequisitionStatus
    application_deadline: date | None
    active_candidate_count: int
    # active + flagged candidates; a posting is deletable only at zero
    in_flight_candidate_count: int
    # every application ever, quoted by the delete confirmation
    application_count: int


class RequisitionDetail(BaseModel):
    id: int
    title: str
    department: str
    description: str | None
    qualifications: str | None
    requirements: str | None
    additional_sections: list[JobDescriptionSection]
    jd_filename: str | None
    application_deadline: date | None
    status: RequisitionStatus
    workflow_definition: list[str]
    # per-job display label for each generic interview_round_k slot in
    # use -- see stage_labels.resolve_stage_label()
    interview_round_labels: dict[str, str] | None
    # same idea, for the generic examination_k slots
    examination_labels: dict[str, str] | None
    # minutes per interview round in this workflow -- what HR saved, else
    # the default (domain.interview_slots.round_duration), so every
    # round in the workflow has one
    interview_durations: dict[str, int] = {}
    # HR-authored AI Pre-Screening questions -- see PreScreeningQuestion
    pre_screening_questions: list[PreScreeningQuestion]
    # applications with status=active; the Workflow Builder locks the
    # stage order while this is > 0, since their stage rows depend on it
    active_candidate_count: int


class DuplicateJobCheck(BaseModel):
    """GET /hr/requisitions/duplicate-check: whether a live job already
    has this title in this department, and the same message the create
    route would refuse it with."""

    duplicate: bool
    message: str | None = None


class WorkflowUpdateRequest(BaseModel):
    """Workflow Builder save: the ordered stage list, round/exam labels
    and interview round lengths."""

    stages: list[StageType] = Field(min_length=1)
    interview_round_labels: dict[str, str] | None = None
    examination_labels: dict[str, str] | None = None
    # minutes per interview round -- editable even while the sequence is
    # locked, like the labels
    interview_durations: dict[str, int] | None = None

    @field_validator("interview_durations")
    @classmethod
    def durations_are_allowed(cls, durations: dict[str, int] | None) -> dict[str, int] | None:
        return _check_durations(durations)

    @field_validator("stages")
    @classmethod
    def stages_must_be_unique(cls, stages: list[StageType]) -> list[StageType]:
        # dfa.build_transition_table() keys by stage, so a repeated stage
        # would silently corrupt it; refuse it here
        if len(set(stages)) != len(stages):
            raise ValueError("Each stage may only appear once in a workflow.")
        return stages


class WorkflowValidationRequest(BaseModel):
    """A proposed stage list for the Workflow Builder's live checklist.
    No `min_length`: even an empty draft is checked, and the rules report
    what is missing."""

    stages: list[StageType] = Field(default_factory=list)


class WorkflowIssueRead(BaseModel):
    """One finding from app.domain.workflow_rules — the single source of
    truth both this endpoint and the save-time block read, so the live
    checklist can never describe a different rule than the one enforced."""

    severity: Literal["error", "warning"]
    code: str
    message: str


class WorkflowValidationResponse(BaseModel):
    issues: list[WorkflowIssueRead]


# RequisitionCreateRequest names PreScreeningQuestion before it is defined.
RequisitionCreateRequest.model_rebuild()
