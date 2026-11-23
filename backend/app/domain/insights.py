"""The facts HR asks for, derived by rule from recorded numbers, never by
a model: they are the Decision Brief Agent's only input. Pure.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.scorecard import SCORECARD_CATEGORIES, TIER_LABELS, compute_tier

# the one flag threshold: skill_matching flags on it, and the wording
# HR reads is anchored on it
MATCH_FLAG_THRESHOLD = 60.0

# half a rating point -- smaller than the gap between any two adjacent
# ratings, so it can only be reached by a real disagreement, not rounding
_DIVERGENCE_THRESHOLD = 0.5

# the widest gap must beat the next by this much to name one category;
# otherwise a uniformly lower rater "diverges" on whichever sorts first
_CATEGORY_MARGIN = 0.25

__all__ = [
    "MATCH_FLAG_THRESHOLD",
    "AspectScore",
    "AgreementRead",
    "RoundRead",
    "aspect_scores",
    "band_label",
    "evaluator_agreement",
    "match_reading",
    "ordinal",
]


def ordinal(n: int) -> str:
    """1 -> "1st". Used wherever a candidate's standing in a cohort is
    written for a person to read ("3rd of 12")."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


@dataclass(frozen=True)
class AspectScore:
    """One HRD-F-APIEF category, averaged across every round that has a
    submitted scorecard."""

    code: str
    label: str
    # Mean on the form's own 1-5 item scale.
    mean: float
    # The form's General Evaluation band for that mean.
    band: str
    # How many rounds contributed, and how many individual item ratings
    # went into the mean — so a category averaged from one round's two
    # items is never mistaken for a settled judgement.
    rounds_counted: int
    items_rated: int


@dataclass(frozen=True)
class RoundRead:
    """One interview round as HR reads it: who evaluated, what they
    concluded, and whether they broke from the others."""

    stage_type: str
    label: str
    evaluator_name: str | None
    score: float | None
    tier: str | None
    tier_label: str | None
    recommendation: str | None
    is_outlier: bool
    evaluator_avatar_url: str | None = None


@dataclass(frozen=True)
class AgreementRead:
    submitted_rounds: int
    total_rounds: int
    unanimous: bool
    # One line HR can read without decoding anything.
    summary: str
    rounds: list[RoundRead]


def _rated_items(ratings: dict | None) -> dict[str, int]:
    """Item ratings that carry a number. A None (N/A on the older form)
    is excluded, never counted as zero, as in scorecard.compute_score."""
    if not ratings:
        return {}
    return {code: value for code, value in ratings.items() if isinstance(value, int)}


def _submitted(interview_ratings: dict[str, dict]) -> list[tuple[str, dict]]:
    """Rounds with a scorecard actually submitted, in workflow order.

    Only those with item ratings: an older-form evaluation has none to
    break down by category, so it is skipped rather than guessed at."""
    return [
        (stage_type, rating)
        for stage_type, rating in interview_ratings.items()
        if _rated_items(rating.get("item_ratings"))
    ]


def band_label(mean: float) -> str:
    """The printed form's own band name for a 1-5 mean."""
    return TIER_LABELS[compute_tier(mean)]


def aspect_scores(interview_ratings: dict[str, dict]) -> list[AspectScore]:
    """Each of the form's four categories, averaged across every
    submitted round. Driven by SCORECARD_CATEGORIES so the item-to-
    category mapping never drifts from the form.

    Only categories with at least one rated item: an unassessed one is
    left out rather than shown as a zero.
    """
    submitted = _submitted(interview_ratings)
    if not submitted:
        return []

    scores: list[AspectScore] = []
    for category in SCORECARD_CATEGORIES:
        values: list[int] = []
        rounds_counted = 0
        for _stage_type, rating in submitted:
            rated = _rated_items(rating.get("item_ratings"))
            in_category = [rated[item.code] for item in category.items if item.code in rated]
            if in_category:
                values.extend(in_category)
                rounds_counted += 1
        if not values:
            continue
        mean = round(sum(values) / len(values), 2)
        scores.append(
            AspectScore(
                code=category.code,
                label=category.label,
                mean=mean,
                band=band_label(mean),
                rounds_counted=rounds_counted,
                items_rated=len(values),
            )
        )
    return scores


def _category_mean(rating: dict, category) -> float | None:
    rated = _rated_items(rating.get("item_ratings"))
    values = [rated[item.code] for item in category.items if item.code in rated]
    return sum(values) / len(values) if values else None


def _divergent_category(outlier: dict, others: list[dict]) -> tuple[str, float] | None:
    """Which single category the outlier round read differently from the
    rest, if there is one.

    None when nothing clears _DIVERGENCE_THRESHOLD, or when the widest gap
    is not meaningfully wider than the next (_CATEGORY_MARGIN); that case
    reads "across the rubric generally".
    """
    gaps: list[tuple[str, float]] = []
    for category in SCORECARD_CATEGORIES:
        mine = _category_mean(outlier, category)
        theirs = [m for m in (_category_mean(o, category) for o in others) if m is not None]
        if mine is None or not theirs:
            continue
        gaps.append((category.label, abs(mine - sum(theirs) / len(theirs))))

    if not gaps:
        return None
    gaps.sort(key=lambda pair: pair[1], reverse=True)
    widest = gaps[0]
    if widest[1] < _DIVERGENCE_THRESHOLD:
        return None
    runner_up = gaps[1][1] if len(gaps) > 1 else 0.0
    if widest[1] - runner_up < _CATEGORY_MARGIN:
        return None
    return widest[0], round(widest[1], 2)


def evaluator_agreement(interview_ratings: dict[str, dict]) -> AgreementRead:
    """Did the interview chain agree, and if not, who broke from it and
    on what.

    Disagreement is reported as information, not fault.
    """
    total_rounds = len(interview_ratings)
    scored = [
        (stage_type, rating)
        for stage_type, rating in interview_ratings.items()
        if rating.get("computed_score") is not None
    ]

    def _round_read(stage_type: str, rating: dict, *, outlier: bool = False) -> RoundRead:
        tier = rating.get("tier")
        return RoundRead(
            stage_type=stage_type,
            label=rating.get("label") or stage_type,
            evaluator_name=rating.get("assigned_evaluator_name"),
            evaluator_avatar_url=rating.get("assigned_evaluator_avatar_url"),
            score=rating.get("computed_score"),
            tier=tier,
            tier_label=TIER_LABELS.get(tier) if tier else None,
            recommendation=rating.get("recommendation"),
            is_outlier=outlier,
        )

    if not scored:
        return AgreementRead(
            submitted_rounds=0,
            total_rounds=total_rounds,
            unanimous=False,
            summary="No interview round has been evaluated yet.",
            rounds=[_round_read(s, r) for s, r in interview_ratings.items()],
        )

    if len(scored) == 1:
        stage_type, rating = scored[0]
        name = rating.get("assigned_evaluator_name") or "The evaluator"
        tier_label = TIER_LABELS.get(rating.get("tier"), "a rating")
        remaining = total_rounds - 1
        summary = f"{name} rated this candidate {tier_label}."
        if remaining > 0:
            summary += (
                f" {remaining} further "
                f"{'round is' if remaining == 1 else 'rounds are'} still outstanding, "
                f"so there is nothing to compare against yet."
            )
        return AgreementRead(
            submitted_rounds=1,
            total_rounds=total_rounds,
            unanimous=False,
            summary=summary,
            rounds=[_round_read(s, r, outlier=False) for s, r in interview_ratings.items()],
        )

    tiers = {r.get("tier") for _s, r in scored}
    scores = [r["computed_score"] for _s, r in scored]
    mean = sum(scores) / len(scores)

    if len(tiers) == 1:
        tier_label = TIER_LABELS.get(next(iter(tiers)), "the same band")
        summary = (
            f"All {len(scored)} evaluators independently placed this candidate "
            f"in the same band: {tier_label}."
        )
        return AgreementRead(
            submitted_rounds=len(scored),
            total_rounds=total_rounds,
            unanimous=True,
            summary=summary,
            rounds=[_round_read(s, r) for s, r in interview_ratings.items()],
        )

    # distance from the mean either way: a much higher rating counts too
    outlier_stage, outlier_rating = max(
        scored, key=lambda pair: abs(pair[1]["computed_score"] - mean)
    )
    others = [r for s, r in scored if s != outlier_stage]
    name = outlier_rating.get("assigned_evaluator_name") or outlier_rating.get("label") or "One evaluator"
    direction = "lower" if outlier_rating["computed_score"] < mean else "higher"
    summary = (
        f"The evaluators did not fully agree. {name} rated this candidate "
        f"{direction} than the others "
        f"({outlier_rating['computed_score']:g} of 5, against "
        f"{sum(o['computed_score'] for o in others) / len(others):.1f} elsewhere)"
    )
    divergent = _divergent_category(outlier_rating, others)
    summary += f", mostly on {divergent[0]}." if divergent else ", across the rubric generally."

    return AgreementRead(
        submitted_rounds=len(scored),
        total_rounds=total_rounds,
        unanimous=False,
        summary=summary,
        rounds=[
            _round_read(s, r, outlier=(s == outlier_stage and r.get("computed_score") is not None))
            for s, r in interview_ratings.items()
        ],
    )


def match_reading(score: float | None) -> str:
    """What the skill match number means, in words, with bands anchored on
    MATCH_FLAG_THRESHOLD so the wording matches what the system does."""
    if score is None:
        return "Not scored yet. The candidate has not completed pre-screening."
    if score < MATCH_FLAG_THRESHOLD:
        return (
            f"Below the {MATCH_FLAG_THRESHOLD:g}-point review threshold, so this "
            f"application was flagged for HR to look at rather than advanced unremarked."
        )
    if score >= 80:
        return "A strong match against this job's stated requirements."
    if score >= 70:
        return "A solid match against this job's stated requirements."
    return (
        f"Above the {MATCH_FLAG_THRESHOLD:g}-point review threshold, but not by much — "
        f"worth reading the gaps below."
    )
