"""Interview rounds: scheduling, the slots HR sends, evaluator assignment
and the job's evaluator pool, and reschedule requests.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.dfa import is_interview_stage
from app.domain.schedule_time import ensure_not_in_past
from app.models.enums import StageType


class InterviewScheduleRequest(BaseModel):
    """HR sets the date, time and place (or an online link) for one of a
    job's interview rounds."""

    stage_type: StageType
    date: str
    time: str
    mode: Literal["in_person", "online"] = "in_person"
    location: str | None = None
    meeting_link: str | None = None

    @field_validator("stage_type")
    @classmethod
    def stage_must_be_an_interview_round(cls, stage_type: StageType) -> StageType:
        if not is_interview_stage(stage_type.value):
            raise ValueError("stage_type must be an interview round.")
        return stage_type

    @model_validator(mode="after")
    def location_or_meeting_link_required(self) -> "InterviewScheduleRequest":
        if self.mode == "in_person" and not (self.location and self.location.strip()):
            raise ValueError("location is required when mode is in_person.")
        if self.mode == "online" and not (
            self.meeting_link and self.meeting_link.strip().startswith(("http://", "https://"))
        ):
            raise ValueError("meeting_link (a valid http/https URL) is required when mode is online.")
        return self

    @model_validator(mode="after")
    def not_in_the_past(self) -> "InterviewScheduleRequest":
        ensure_not_in_past(self.date, self.time)
        return self


class InterviewSlotRef(BaseModel):
    """One fixed slot by its start: the date and HH:MM it begins."""

    date: str
    time: str


class InterviewSlotOfferRequest(BaseModel):
    """HR sends the evaluator's free slots it kept ticked to the applicant,
    and where the interview happens. The same where-rules as InterviewScheduleRequest."""

    stage_type: StageType
    slots: list[InterviewSlotRef] = Field(min_length=1, max_length=200)
    mode: Literal["in_person", "online"] = "in_person"
    location: str | None = None
    meeting_link: str | None = None

    @field_validator("stage_type")
    @classmethod
    def stage_must_be_an_interview_round(cls, stage_type: StageType) -> StageType:
        if not is_interview_stage(stage_type.value):
            raise ValueError("stage_type must be an interview round.")
        return stage_type

    @model_validator(mode="after")
    def location_or_meeting_link_required(self) -> "InterviewSlotOfferRequest":
        if self.mode == "in_person" and not (self.location and self.location.strip()):
            raise ValueError("Enter where the interview takes place.")
        if self.mode == "online" and not (
            self.meeting_link and self.meeting_link.strip().startswith(("http://", "https://"))
        ):
            raise ValueError("Enter the meeting link (starting with http:// or https://).")
        return self


class EvaluatorAccountRead(BaseModel):
    """An evaluator account, for GET /hr/evaluators (the Workflow
    Builder's evaluator-pool picker). Accounts are created by invite
    (schemas.invite)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    created_at: datetime


class RequisitionEvaluatorRead(BaseModel):
    """One member of a job's evaluator pool."""

    id: int
    evaluator_id: int
    full_name: str
    email: str
    avatar_url: str | None = None
    # what they set on their own Account Settings -- shown in the pool so
    # HR can tell who is who by role, not just by name
    job_title: str | None = None
    department: str | None = None
    # true once they have scored any of this job's candidates; the
    # Workflow Builder then hides "remove" so history isn't dropped on a
    # stray click
    has_conducted: bool = False
    # false once a super admin has switched their account off. They stay
    # in the pool (their history on the job stays), but can't be given a
    # new interview; the Workflow Builder and the Interviews tab say so.
    is_active: bool = True


class RequisitionEvaluatorAddRequest(BaseModel):
    evaluator_id: int


class InterviewAssignmentRequest(BaseModel):
    """HR assigns (or, with evaluator_id=None, unassigns) a specific pool
    member to conduct a specific candidate's specific interview round."""

    stage_type: StageType
    evaluator_id: int | None

    @field_validator("stage_type")
    @classmethod
    def stage_must_be_an_interview_round(cls, stage_type: StageType) -> StageType:
        if not is_interview_stage(stage_type.value):
            raise ValueError("stage_type must be an interview round.")
        return stage_type


class RescheduleResolveRequest(BaseModel):
    """HR's verdict on an evaluator's reschedule request. date/time are
    only used (and required) on approve -- they let HR accept the
    evaluator's exact proposal, or set a different time instead, in the
    same action; a deny leaves the existing schedule untouched."""

    decision: Literal["approve", "deny"]
    date: str | None = None
    time: str | None = None

    @model_validator(mode="after")
    def date_and_time_required_on_approve(self) -> "RescheduleResolveRequest":
        if self.decision == "approve" and not (self.date and self.time):
            raise ValueError("date and time are required to approve a reschedule request.")
        if self.decision == "approve":
            ensure_not_in_past(self.date, self.time)
        return self
