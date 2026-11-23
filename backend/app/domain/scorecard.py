"""The Applicant Preliminary Interview Evaluation Form (MSEUF HRD-F-APIEF,
Rev 2, July 2023) and its scoring; hardcoded because it is a signed form.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

GeneralEvaluationTier = Literal["highly_qualified", "qualified", "not_qualified"]

# the evaluator's own overall call, chosen on the form, never derived
# from the ratings. It may disagree with GeneralEvaluationTier (the
# ratings' banded mean), and that disagreement is information. These
# labels are ARKIVE's addition; the printed form has only the tier bands.
EvaluatorRecommendation = Literal["highly_recommended", "recommended", "not_recommended"]

RECOMMENDATION_LABELS: dict[str, str] = {
    "highly_recommended": "Highly Recommended",
    "recommended": "Recommended",
    "not_recommended": "Not Recommended",
}

# lives here (not just the frontend) so anything the backend writes for
# a human to read -- the Decision Brief's facts block, insights.py --
# uses the institution's own vocabulary instead of inventing a parallel one
TIER_LABELS: dict[str, str] = {
    "highly_qualified": "Highly Qualified",
    "qualified": "Qualified",
    "not_qualified": "Not Qualified",
}


@dataclass(frozen=True)
class ScorecardItem:
    code: str
    label: str


@dataclass(frozen=True)
class ScorecardCategory:
    code: str
    label: str
    items: tuple[ScorecardItem, ...]


SCORECARD_CATEGORIES: tuple[ScorecardCategory, ...] = (
    ScorecardCategory(
        code="A",
        label="Personal Background",
        items=(
            ScorecardItem("A1", "Ability to provide personal information"),
            ScorecardItem("A2", "Personal background fitted to the job applied for"),
        ),
    ),
    ScorecardCategory(
        code="B",
        label="Educational Qualifications",
        items=(
            ScorecardItem("B1", "Educational background appropriate to the vacancy to be fitted"),
            ScorecardItem(
                "B2",
                "Confident that his/her educational background will meet the needs of the job applied for",
            ),
        ),
    ),
    ScorecardCategory(
        code="C",
        label="Work Background",
        items=(
            ScorecardItem("C1", "Previous work background"),
            ScorecardItem("C2", "Reasons for leaving previous job"),
            ScorecardItem("C3", "Work references/professional references"),
        ),
    ),
    ScorecardCategory(
        code="D",
        label="Job Expectations",
        items=(
            ScorecardItem("D1", "Knowledge and reasons for applying MSEUF"),
            ScorecardItem("D2", "Expectations of job applied for"),
            ScorecardItem("D3", "Salary or wage expectations"),
            ScorecardItem("D4", "Career development and leadership potential"),
        ),
    ),
)

SCORECARD_ITEM_CODES: tuple[str, ...] = tuple(
    item.code for category in SCORECARD_CATEGORIES for item in category.items
)


def compute_score(item_ratings: dict[str, int | None]) -> float:
    """Mean of the non-null (non-N/A) item ratings. EvaluationRequest's
    validator rejects an all-N/A submission before this ever runs, so
    this never divides by zero."""
    rated = [r for r in item_ratings.values() if r is not None]
    return round(sum(rated) / len(rated), 2)


def compute_tier(score: float) -> GeneralEvaluationTier:
    """Reproduces the form's own General Evaluation bands exactly:
    Highly Qualified (5), Qualified (4-3), Not Qualified (2-1). Every item
    rating is capped at 5, so a computed_score of exactly 5.0 only occurs
    when every rated item scored 5 — matching the form's single-point "5"
    band rather than a range."""
    if score >= 5:
        return "highly_qualified"
    if score >= 3:
        return "qualified"
    return "not_qualified"
