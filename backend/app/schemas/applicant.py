from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.dfa import is_exam_stage, is_interview_stage
from app.models.enums import ApplicationStatus, StageStatus, StageType
from app.schemas.application_document import ApplicationDocumentRead
from app.schemas.pipeline import PreScreeningQuestion
from app.schemas.resume import ApplicationResumeRead


class ApplyRequest(BaseModel):
    requisition_id: int


class StageInstanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage_type: StageType
    # filled in by _to_detail() after validation (stage_labels.
    # resolve_stage_label), so applicants see the job's own label
    label: str = ""
    status: StageStatus
    payload: dict | None
    completed_at: datetime | None


class ExamSlotOption(BaseModel):
    """One exam session the applicant can still pick in their
    Examination stage: not started, with a seat left."""

    id: int
    date: str
    time: str
    end_time: str | None = None
    location: str
    remaining_capacity: int


class ExamBookingSummary(BaseModel):
    """The exam session the applicant is booked in, for the exam stage
    they're on, and whether they can still change it themselves (until
    24 hours before it starts)."""

    stage_type: StageType
    slot_id: int
    date: str
    time: str
    end_time: str | None = None
    location: str
    can_change: bool


class ExamNoneWorkRead(BaseModel):
    """The applicant told HR that none of the open sessions work."""

    note: str | None = None
    at: str


class InterviewSlotOption(BaseModel):
    """One fixed interview slot the applicant can pick."""

    date: str
    time: str
    end_time: str


class InterviewSlotOfferRead(BaseModel):
    """The times HR sent for the interview round the applicant is on.
    `slots` is only what is
    still free right now. `response` is "none_work" once they've told HR
    none of them suit, and None while it is still theirs to answer."""

    stage_type: StageType
    duration_minutes: int
    mode: Literal["in_person", "online"]
    location: str | None = None
    slots: list[InterviewSlotOption]
    response: str | None = None
    note: str | None = None


class ApplicantExamResult(BaseModel):
    """One exam stage's score as HR recorded it, for the applicant. Unlike
    the AI's analysis, an exam score and rank are plain facts, so the
    applicant sees them."""

    label: str
    score: float


class OfferRead(BaseModel):
    """The offer window on an accepted application -- deadline, and the
    applicant's answer once they give one.

    Its own field because the final_decision payload is never shown to
    the applicant (it holds HR's working); the offer is the part addressed
    to them. None when there is no live offer."""

    deadline: datetime
    window_days: int
    # accepted | declined | expired, or None while still open and
    # unanswered. `expired` is written by the lazy expiry check, never by
    # the applicant.
    response: str | None = None
    responded_at: datetime | None = None


class ScheduleConfirmationRequest(BaseModel):
    """The applicant's answer to "can you make this time?".

    `note` is an optional line for HR when the applicant is unavailable.
    """

    stage_type: StageType
    response: Literal["confirmed", "unavailable"]
    note: str = ""


class ShortlistingAcceptanceRead(BaseModel):
    """What the applicant's Accept / Decline screen reads. `response` is
    None while it is still theirs to answer."""

    response: str | None = None
    opened_at: str | None = None
    responded_at: str | None = None


class ApplicationDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # which job this is an application to -- the job browser marks the
    # positions someone has already applied to by it
    requisition_id: int
    job_title: str
    job_department: str
    current_stage: StageType | None
    status: ApplicationStatus
    stage_instances: list[StageInstanceRead]
    # None until the applicant has submitted the document_upload stage.
    resume: ApplicationResumeRead | None = None
    pre_screening_questions: list[PreScreeningQuestion] = []
    # The sessions the applicant can book for the exam stage they are on:
    # while it's unbooked, or while they can still change their booking
    # (then without the one they're in). Empty otherwise -- computing seat
    # counts for every historical application on every dashboard load
    # would be wasted work.
    exam_sessions: list[ExamSlotOption] = []
    # the session they're booked in, while on that exam stage -- with
    # exam_sessions then holding the other sessions they could change to
    exam_booking: ExamBookingSummary | None = None
    # set once they've said none of the open sessions work
    exam_none_work: ExamNoneWorkRead | None = None
    # The interview times HR sent for the round they are on, while it
    # isn't booked yet -- None otherwise.
    interview_slot_offer: InterviewSlotOfferRead | None = None
    # only populated once HR has recorded at least one exam score for
    # this application. exam_percentile mirrors the same Algorithm 03
    # calc CandidateProfile.exam_percentile computes for HR.
    examination_results: dict[str, ApplicantExamResult] = {}
    exam_percentile: float | None = None
    # supplemental documents (reference letters, updated portfolio, etc.)
    # added after the initial document_upload submission -- distinct
    # from `resume` above, the single required one
    documents: list[ApplicationDocumentRead] = []
    # The offer-response window, once HR has accepted this applicant —
    # None otherwise (and None for a legacy hire that predates offers).
    offer: OfferRead | None = None
    # The confirmation a shortlisted candidate owes before they sit the
    # examination. None when they were not shortlisted, when the job has
    # no shortlisting stage, or when they were shortlisted before this
    # existed — in which case nothing is asked of them and the stage
    # advances the way it always did.
    shortlisting_acceptance: ShortlistingAcceptanceRead | None = None


class OfferResponseRequest(BaseModel):
    """Free-text reason, applicant's own words, only meaningful on a
    decline. Optional on purpose -- forcing one just produces "n/a"
    typed a thousand times, same reasoning as the hire decision's
    reason."""

    reason: str | None = None


class PreScreeningAnswer(BaseModel):
    # a PreScreeningQuestion.id, so the answer survives HR editing the list
    question_id: str
    value: str


class ExamNoneWorkRequest(BaseModel):
    """The applicant can't make any of the open sessions -- HR is told."""

    stage_type: StageType
    note: str | None = Field(default=None, max_length=500)

    @field_validator("stage_type")
    @classmethod
    def stage_must_be_an_exam(cls, stage_type: StageType) -> StageType:
        if not is_exam_stage(stage_type.value):
            raise ValueError("stage_type must be an examination stage.")
        return stage_type


class ExamBookingRequest(BaseModel):
    """The exam session the applicant picked for the exam stage they are
    on. Booked at once -- no HR approval."""

    stage_type: StageType
    exam_slot_id: int

    @field_validator("stage_type")
    @classmethod
    def stage_must_be_an_exam(cls, stage_type: StageType) -> StageType:
        if not is_exam_stage(stage_type.value):
            raise ValueError("stage_type must be an examination stage.")
        return stage_type


class InterviewSlotPickRequest(BaseModel):
    """The interview slot the applicant picked -- picking confirms it."""

    stage_type: StageType
    date: str
    time: str

    @field_validator("stage_type")
    @classmethod
    def stage_must_be_an_interview_round(cls, stage_type: StageType) -> StageType:
        if not is_interview_stage(stage_type.value):
            raise ValueError("stage_type must be an interview round.")
        return stage_type


class InterviewSlotDeclineRequest(BaseModel):
    """None of the sent times work -- with an optional line for HR, the
    same courtesy as ScheduleConfirmationRequest's note."""

    stage_type: StageType
    note: str = ""

    @field_validator("stage_type")
    @classmethod
    def stage_must_be_an_interview_round(cls, stage_type: StageType) -> StageType:
        if not is_interview_stage(stage_type.value):
            raise ValueError("stage_type must be an interview round.")
        return stage_type


class PreScreeningRequest(BaseModel):
    answers: list[PreScreeningAnswer]


class OnboardingChecklistRequest(BaseModel):
    checklist: dict[str, bool]
