from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.interview_slots import to_minutes
from app.domain.schedule_time import ensure_not_in_past
from app.domain.scorecard import (
    SCORECARD_ITEM_CODES,
    EvaluatorRecommendation,
    GeneralEvaluationTier,
)
from app.schemas.resume import ApplicationResumeRead


class RescheduleRequestRead(BaseModel):
    id: int
    proposed_date: str
    proposed_time: str
    reason: str | None
    status: str
    created_at: datetime


class InterviewListItem(BaseModel):
    stage_instance_id: int
    application_id: int
    applicant_name: str
    applicant_avatar_url: str | None = None
    job_title: str
    # Per-job label for this round (e.g. a custom interview_round_k name)
    # — see app.services.stage_labels.resolve_stage_label().
    stage_label: str
    status: str
    already_evaluated: bool
    # the applicant has confirmed the interview time -- the scorecard is
    # refused until they have
    schedule_confirmed: bool = False


class EvaluationRecord(BaseModel):
    """The stored, submitted scorecard -- server-computed fields
    (computed_score/tier) alongside what the evaluator actually entered
    (item_ratings/remarks)."""

    item_ratings: dict[str, int | None]
    computed_score: float
    tier: GeneralEvaluationTier
    # null only for evaluations from before this field existed.
    # deliberately not back-filled from `tier` -- the two answer
    # different questions, inventing one would put words in a real
    # evaluator's mouth
    recommendation: EvaluatorRecommendation | None = None
    remarks: str
    ai_summary: str
    # Interview Synthesis Agent output -- an independent AI judgment of
    # how thoroughly the remarks/ratings substantiate the rubric, not a
    # rescale of computed_score. feeds WSM's C4 "Interview Rubric Score".
    rubric_coverage_score: float
    submitted_by: int
    submitted_at: datetime


class InterviewDetail(BaseModel):
    stage_instance_id: int
    application_id: int
    applicant_name: str
    applicant_avatar_url: str | None = None
    job_title: str
    stage_type: str
    stage_label: str
    status: str
    resume: ApplicationResumeRead | None
    schedule: dict | None
    evaluation: EvaluationRecord | None
    # this evaluator's pending reschedule request, if any -- None once
    # HR resolves it (CandidateProfile is the historical record for
    # approved/denied ones)
    pending_reschedule_request: RescheduleRequestRead | None
    # the ranges this evaluator is free in for this round, and the
    # round's length they get cut into
    availability: list["AvailabilityWindowRead"] = []
    duration_minutes: int = 45
    # True once HR has sent times to the applicant and they haven't
    # picked yet -- the evaluator's ranges are already out with them
    times_sent: bool = False
    # the applicant has confirmed the interview time; until then the
    # form is shown disabled and the scorecard is refused (#13)
    schedule_confirmed: bool = False


class EvaluationRequest(BaseModel):
    """The Applicant Preliminary Interview Evaluation Form (HRD-F-APIEF): every
    one of the 11 canonical items must be present and rated 1-5. There is no
    N/A; scorecards from the older form may still hold null, which
    app.domain.scorecard keeps skipping. computed_score/tier are derived
    server-side from this, not submitted directly — see
    app.domain.scorecard."""

    item_ratings: dict[str, int | None]
    remarks: str
    # required because on the paper form this box isn't optional -- an
    # unchecked General Evaluation section is an incomplete submission.
    # distinct from the derived `tier` -- see scorecard.
    # EvaluatorRecommendation for why both exist and can disagree.
    recommendation: EvaluatorRecommendation

    @field_validator("item_ratings")
    @classmethod
    def _validate_item_ratings(cls, v: dict[str, int | None]) -> dict[str, int | None]:
        if set(v.keys()) != set(SCORECARD_ITEM_CODES):
            raise ValueError("item_ratings must include exactly the 11 canonical scorecard items.")
        for code, rating in v.items():
            if rating is None or not (1 <= rating <= 5):
                raise ValueError(f"{code}: every item must be rated 1-5.")
        return v


class RescheduleRequestCreate(BaseModel):
    proposed_date: str
    proposed_time: str
    reason: str | None = None

    @model_validator(mode="after")
    def not_in_the_past(self) -> "RescheduleRequestCreate":
        ensure_not_in_past(self.proposed_date, self.proposed_time)
        return self


class AvailabilityWindowRead(BaseModel):
    """One range the evaluator is free in, e.g. 2026-10-20 09:00-12:00."""

    date: str
    start: str
    end: str


class AvailabilityWindow(AvailabilityWindowRead):
    """A range being saved: still to come, and ending after it starts."""

    @model_validator(mode="after")
    def a_real_range_still_to_come(self) -> "AvailabilityWindow":
        ensure_not_in_past(self.date, self.start)
        try:
            start, end = to_minutes(self.start), to_minutes(self.end)
        except ValueError as exc:
            raise ValueError("Enter each time as HH:MM.") from exc
        if end <= start:
            raise ValueError("Each range has to end after it starts.")
        return self


class AvailabilityUpdateRequest(BaseModel):
    """The evaluator's whole set of free ranges for one round -- it
    replaces what was there, so removing a range is just leaving it out.
    An empty list clears them."""

    windows: list[AvailabilityWindow] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def ranges_dont_overlap(self) -> "AvailabilityUpdateRequest":
        spans = sorted((w.date, to_minutes(w.start), to_minutes(w.end)) for w in self.windows)
        for (day, _, earlier_end), (next_day, later_start, _) in zip(spans, spans[1:]):
            if day == next_day and later_start < earlier_end:
                raise ValueError("Two of your ranges on the same day overlap. Merge them into one.")
        return self


InterviewDetail.model_rebuild()
