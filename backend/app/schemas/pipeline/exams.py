"""Examination sessions: the sessions, their rosters, HR's bookings and
older pending proposals.
"""

from datetime import time
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.dfa import is_exam_stage
from app.domain.schedule_time import ensure_not_in_past
from app.models.enums import StageType


class ExamSessionAttendee(BaseModel):
    """One person holding a seat in a session -- a row of HR's roster."""

    application_id: int
    applicant_name: str
    avatar_url: str | None = None


class ExamSlotRead(BaseModel):
    """One exam session -- remaining_capacity is seats left: capacity
    minus every booking that holds a seat (an old pending proposal holds
    one too, so the session can't be oversold). `booked` is the roster."""

    id: int
    stage_type: str
    date: str
    time: str
    end_time: str | None = None
    location: str
    capacity: int
    remaining_capacity: int
    booked: list[ExamSessionAttendee] = []


class ExamSessionBatchResult(BaseModel):
    """What "Add sessions" made, and how many it left out because the job
    already had that exact session (same exam, date, time and place)."""

    created: list[ExamSlotRead]
    skipped: int


class ExamSessionUpdateRequest(BaseModel):
    """HR's edit of one session.
    Everyone booked in it is told when its date, time or place changes."""

    date: str
    start: str
    end: str
    location: str = Field(min_length=1, max_length=255)
    seats: int = Field(ge=1, le=500)

    @field_validator("location")
    @classmethod
    def location_not_blank(cls, location: str) -> str:
        if not location.strip():
            raise ValueError("Enter where the exam takes place.")
        return location.strip()

    @model_validator(mode="after")
    def a_sensible_window(self) -> "ExamSessionUpdateRequest":
        ExamSessionWindow(start=self.start, end=self.end)
        ensure_not_in_past(self.date, self.start)
        return self


class HrExamBookingRequest(BaseModel):
    """HR books an applicant into one of the job's sessions, or moves them
    to another. HR isn't held to the applicant's 24-hour cut-off, but is
    held to the seat limit."""

    stage_type: StageType
    exam_slot_id: int

    @field_validator("stage_type")
    @classmethod
    def stage_must_be_an_exam(cls, stage_type: StageType) -> StageType:
        if not is_exam_stage(stage_type.value):
            raise ValueError("stage_type must be an examination stage.")
        return stage_type


class ExamBookingCandidateSlot(BaseModel):
    """One of the applicant's own eligible picks, resolved to a full
    object so HR's approval UI can offer an alternative without a second
    round-trip."""

    id: int
    date: str
    time: str
    location: str


class ExamBookingRead(BaseModel):
    """A pending Exam Scheduling agent proposal, surfaced on the
    Candidate Profile so HR can review it before the applicant has even
    reached the exam stage."""

    id: int
    proposed_slot_id: int
    candidate_slots: list[ExamBookingCandidateSlot]


class ExamBookingResolveRequest(BaseModel):
    """HR's verdict on a pending exam-slot proposal. exam_slot_id
    defaults to the agent's own proposed slot on approve, but HR can pick
    a different one of the applicant's eligible choices instead -- same
    shape as RescheduleResolveRequest. Unused on deny."""

    decision: Literal["approve", "deny"]
    exam_slot_id: int | None = None


class ExamSlotCreateRequest(BaseModel):
    stage_type: StageType
    date: str
    time: str
    location: str
    capacity: int = Field(ge=1)

    @field_validator("stage_type")
    @classmethod
    def stage_must_be_an_exam(cls, stage_type: StageType) -> StageType:
        if not is_exam_stage(stage_type.value):
            raise ValueError("stage_type must be an examination stage.")
        return stage_type

    @model_validator(mode="after")
    def not_in_the_past(self) -> "ExamSlotCreateRequest":
        ensure_not_in_past(self.date, self.time)
        return self


class ExamSessionWindow(BaseModel):
    """One time window an exam session runs in, e.g. 09:00-11:30."""

    start: str
    end: str

    @model_validator(mode="after")
    def ends_after_it_starts(self) -> "ExamSessionWindow":
        try:
            start, end = time.fromisoformat(self.start), time.fromisoformat(self.end)
        except ValueError as exc:
            raise ValueError("Enter each time as HH:MM.") from exc
        if end <= start:
            raise ValueError("Each time window has to end after it starts.")
        return self


class ExamSessionBatchRequest(BaseModel):
    """HR's "Add sessions": every date crossed with every time window, each
    with the same seats and place, created together."""

    stage_type: StageType
    dates: list[str] = Field(min_length=1, max_length=31)
    windows: list[ExamSessionWindow] = Field(min_length=1, max_length=6)
    seats: int = Field(ge=1, le=500)
    location: str = Field(min_length=1, max_length=255)

    @field_validator("stage_type")
    @classmethod
    def stage_must_be_an_exam(cls, stage_type: StageType) -> StageType:
        if not is_exam_stage(stage_type.value):
            raise ValueError("stage_type must be an examination stage.")
        return stage_type

    @field_validator("location")
    @classmethod
    def location_not_blank(cls, location: str) -> str:
        if not location.strip():
            raise ValueError("Enter where the exam takes place.")
        return location.strip()

    @model_validator(mode="after")
    def sessions_are_sensible(self) -> "ExamSessionBatchRequest":
        if len(set(self.dates)) != len(self.dates):
            raise ValueError("Each date can only be picked once.")
        spans = sorted((w.start, w.end) for w in self.windows)
        for (_, earlier_end), (later_start, _) in zip(spans, spans[1:]):
            if later_start < earlier_end:
                raise ValueError("Time windows can't overlap.")
        for day in self.dates:
            for window in self.windows:
                ensure_not_in_past(day, window.start)
        return self
