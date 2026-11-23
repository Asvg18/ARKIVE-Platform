"""The Interview Synthesis Agent's output shape
(services/interview_synthesis.py)."""

from pydantic import BaseModel


class InterviewSynthesisResult(BaseModel):
    """rubric_coverage_score (0-100) is an independent AI judgment of how
    thoroughly the evaluator's own remarks/ratings demonstrate coverage
    of the scorecard's four categories -- deliberately not a rescale of
    computed_score (the human's 1-5 average), so it stays a genuinely
    separate signal for the WSM's C4 input."""

    rubric_coverage_score: float
    summary: str
