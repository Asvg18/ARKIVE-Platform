"""Requests and results for moving and deciding on applications:
stage transitions, status and flag decisions, exam and shortlisting
outcomes, and the bulk shortlist.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.dfa import is_exam_stage
from app.domain.schedule_time import ensure_not_in_future
from app.models.enums import ApplicationStatus, StageType


class TransitionRequest(BaseModel):
    """`acknowledged_incomplete` and `reason` are the same override as
    StatusUpdateRequest's, for every stage before the final decision. Both
    default to the safe value: a client that omits them is refused."""

    target_stage: StageType
    acknowledged_incomplete: bool = False
    reason: str | None = None


class TransitionResponse(BaseModel):
    application_id: int
    previous_stage: StageType | None
    current_stage: StageType


class ApplicationListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    applicant_name: str
    applicant_avatar_url: str | None = None
    job_title: str
    # the board shows one job at a time: columns are that job's stages
    requisition_id: int
    current_stage: StageType | None
    # resolves a per-job custom interview_round_k label if set, else a
    # sensible default (see stage_labels.resolve_stage_label())
    current_stage_label: str | None
    # per the DFA generated from this job's workflow_definition; None
    # means the application is on its job's terminal stage
    next_stage: StageType | None
    status: ApplicationStatus
    # None until the candidate has actually reached/passed skill_matching
    match_score: float | None
    # the shortlisting call on record, if any, so the bulk-shortlist
    # preview shows an existing decision rather than contradicting it
    shortlisting_outcome: str | None = None


class StatusUpdateRequest(BaseModel):
    """`acknowledged_incomplete` is the deliberate override: HR can hire
    from any stage, but an incomplete record has to be acknowledged, with
    a reason. See services/hire_decision.py."""

    status: ApplicationStatus
    reason: str | None = Field(default=None, max_length=2000)
    acknowledged_incomplete: bool = False


class ResolveFlagRequest(BaseModel):
    """HR's verdict on an application Skill Matching flagged as a weak
    fit. `continue` advances the DFA past skill_matching immediately (the
    applicant already answered AI Pre-Screening, nothing to resubmit).
    `reject` just sets status to rejected, same as the normal
    status-update path."""

    decision: Literal["continue", "reject"]


class ExaminationResultRequest(BaseModel):
    """An exam result HR enters by hand (exams are held outside ARKIVE).
    stage_type names which of the job's exam stages it is for."""

    stage_type: StageType
    score: float = Field(ge=0, le=100)
    # the day the exam was actually sat. The form fills in the booked
    # session's date; left out, the router falls back to that same date.
    taken_on: str | None = None

    @field_validator("stage_type")
    @classmethod
    def stage_must_be_an_exam(cls, stage_type: StageType) -> StageType:
        if not is_exam_stage(stage_type.value):
            raise ValueError("stage_type must be an examination stage.")
        return stage_type

    @field_validator("taken_on")
    @classmethod
    def taken_on_not_in_the_future(cls, taken_on: str | None) -> str | None:
        if taken_on is None or not taken_on.strip():
            return None
        ensure_not_in_future(taken_on.strip())
        return taken_on.strip()


class ShortlistingResultRequest(BaseModel):
    """HR's outcome for the Shortlisting stage, entered by hand."""

    stage_type: StageType
    outcome: Literal["shortlisted", "not_shortlisted"]
    notes: str = ""

    @field_validator("stage_type")
    @classmethod
    def stage_must_be_shortlisting(cls, stage_type: StageType) -> StageType:
        if stage_type != StageType.shortlisting:
            raise ValueError("stage_type must be shortlisting.")
        return stage_type


class ShortlistRequest(BaseModel):
    """One shortlisting decision for a whole job: who HR picked, and the
    two letters that go out either side of that choice.

    **HR names the shortlist; the system does not infer it.** The match
    score is a read on a resume, not a ranking of people, so there is no
    "top N by score" option: the list is sorted by score as guidance, but
    nothing is selected on HR's behalf.

    Everyone awaiting a decision who is *not* named here is recorded as
    not shortlisted. There is no third state: this action exists to
    answer the question for the whole field at once.

    Letters are required for whichever groups have someone in them
    (checked in the endpoint, which knows the split); there is no default
    wording.
    """

    stage_type: StageType
    # an id that is not awaiting a decision on this job is refused, not
    # ignored
    shortlisted_application_ids: list[int] = Field(default_factory=list)
    shortlisted_letter: str = ""
    not_shortlisted_letter: str = ""

    @field_validator("stage_type")
    @classmethod
    def stage_must_be_shortlisting(cls, stage_type: StageType) -> StageType:
        if stage_type is not StageType.shortlisting:
            raise ValueError("This endpoint only records the shortlisting stage.")
        return stage_type


class ShortlistedCandidate(BaseModel):
    """One row of the result, including whether the email was sent."""

    application_id: int
    applicant_name: str
    rank: int | None
    match_score: float | None
    outcome: str
    emailed: bool


class ShortlistResult(BaseModel):
    shortlisted: list[ShortlistedCandidate]
    not_shortlisted: list[ShortlistedCandidate]
    # already decided on the profile, so not part of this action; listed
    # so the numbers add up on screen
    already_decided: list[ShortlistedCandidate] = []
    emails_failed: int
