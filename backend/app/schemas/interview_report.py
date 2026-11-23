"""The interview results report. One object serves both the page and the
PDF, so they can never differ.
"""

from datetime import datetime

from pydantic import BaseModel


class InterviewReportRound(BaseModel):
    stage_type: str
    # the job's own name for the round ("HR Interview")
    label: str
    # set when one person ran this round for every ranked candidate, so
    # the report can name them once in the heading instead of in each row
    evaluator_name: str | None


class InterviewReportCell(BaseModel):
    """One candidate's result in one round."""

    stage_type: str
    score: float | None
    # the form's General Evaluation for this round -- Highly Qualified,
    # Qualified or Not Qualified -- as stored on the scorecard
    tier: str | None
    tier_label: str | None
    # the interviewer's own call on the form -- Highly Recommended,
    # Recommended or Not Recommended -- never derived from the score
    recommendation: str | None
    recommendation_label: str | None
    evaluator_name: str | None
    # the round is behind the candidate but has no scorecard -- HR moved
    # them past it without one
    no_scorecard: bool


class InterviewReportEntry(BaseModel):
    rank: int
    application_id: int
    applicant_name: str
    cells: list[InterviewReportCell]
    # the interviewers' scores added up, then divided by how many there
    # are: (interviewer 1 + interviewer 2 + interviewer 3) / 3
    final_score: float
    # a round has no scorecard, so the average is over fewer rounds
    partial: bool


class InterviewReportPending(BaseModel):
    """A candidate still in the interviews. While anyone is, the report
    waits -- a ranking missing someone would read as final and isn't."""

    application_id: int
    applicant_name: str
    # "VP Interview (Teresita Alvarez)", one per round still to come
    waiting_on: list[str]


class InterviewReportExcluded(BaseModel):
    """Reached the interviews but can't be ranked -- withdrew, or the
    application closed before the rounds were done."""

    applicant_name: str
    reason: str


class InterviewReport(BaseModel):
    requisition_id: int
    job_title: str
    department: str
    # false for a job with no interview rounds at all
    has_interviews: bool
    # every candidate who reached the interviews has finished them, and
    # at least one can be ranked
    ready: bool
    rounds: list[InterviewReportRound]
    entries: list[InterviewReportEntry]
    pending: list[InterviewReportPending]
    excluded: list[InterviewReportExcluded]
    generated_at: datetime
    filename: str
