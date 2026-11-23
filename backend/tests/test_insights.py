"""Tests for domain/insights.py -- the pure rules that turn recorded
ratings into the facts HR reads on the synthesis tab.

No DB, no mocking, no model: everything here is arithmetic over the
HRD-F-APIEF rubric, which is the whole point. The Decision Brief Agent is
handed this module's output and nothing else, so if these are right the
brief has nothing false to say.
"""

import pytest

from app.domain.insights import (
    MATCH_FLAG_THRESHOLD,
    aspect_scores,
    band_label,
    evaluator_agreement,
    match_reading,
    ordinal,
)

# A1/A2 Personal Background, B1/B2 Educational Qualifications,
# C1-C3 Work Background, D1-D4 Job Expectations.
ALL_FIVES = {
    "A1": 5, "A2": 5, "B1": 5, "B2": 5, "C1": 5, "C2": 5, "C3": 5,
    "D1": 5, "D2": 5, "D3": 5, "D4": 5,
}


def _round(label, ratings, *, score, tier, name, recommendation="recommended"):
    return {
        "label": label,
        "item_ratings": ratings,
        "computed_score": score,
        "tier": tier,
        "recommendation": recommendation,
        "assigned_evaluator_name": name,
    }


# ---------------------------------------------------------------------------
# aspect_scores
# ---------------------------------------------------------------------------


def test_categories_average_across_every_evaluated_round():
    ratings = {**ALL_FIVES, "C1": 3, "C2": 3, "C3": 3}
    interview_ratings = {
        "interview_round_1": _round("HR", ALL_FIVES, score=5.0, tier="highly_qualified", name="Rosalie"),
        "interview_round_2": _round("Dept", ratings, score=4.45, tier="qualified", name="Armando"),
    }

    by_code = {a.code: a for a in aspect_scores(interview_ratings)}

    # Work Background: three 5s from round 1, three 3s from round 2.
    assert by_code["C"].mean == 4.0
    assert by_code["C"].rounds_counted == 2
    assert by_code["C"].items_rated == 6
    # Every other category was rated 5 in both rounds.
    assert by_code["A"].mean == 5.0
    assert by_code["D"].mean == 5.0


def test_na_items_are_excluded_from_the_mean_not_counted_as_zero():
    """The form treats N/A as "not assessed". Averaging it as a zero
    would punish a candidate for a question the evaluator chose not to
    ask."""
    ratings = {**ALL_FIVES, "C1": 4, "C2": None, "C3": None}
    by_code = {
        a.code: a
        for a in aspect_scores(
            {"interview_round_1": _round("HR", ratings, score=4.9, tier="qualified", name="Rosalie")}
        )
    }

    assert by_code["C"].mean == 4.0
    assert by_code["C"].items_rated == 1


def test_a_category_rated_na_throughout_is_omitted_entirely():
    """No score is not the same as a bad score — an unassessed category
    must not render as an empty bar."""
    ratings = {**ALL_FIVES, "B1": None, "B2": None}
    codes = {
        a.code
        for a in aspect_scores(
            {"interview_round_1": _round("HR", ratings, score=5.0, tier="highly_qualified", name="R")}
        )
    }

    assert "B" not in codes
    assert {"A", "C", "D"} <= codes


def test_legacy_rounds_without_item_ratings_are_skipped():
    """Evaluations predating the HRD-F-APIEF redesign carry a
    computed_score and no item_ratings at all. They cannot be broken down
    by category, so per-aspect scoring skips them rather than inventing a
    distribution."""
    interview_ratings = {
        "interview_round_1": {
            "label": "HR",
            "item_ratings": None,
            "computed_score": 4.0,
            "tier": "qualified",
            "recommendation": None,
            "assigned_evaluator_name": "Legacy",
        }
    }

    assert aspect_scores(interview_ratings) == []
    # ...but the round still counts as evaluated for the agreement read,
    # which only needs computed_score.
    assert evaluator_agreement(interview_ratings).submitted_rounds == 1


def test_no_submitted_rounds_yields_no_aspects():
    assert aspect_scores({}) == []


# ---------------------------------------------------------------------------
# evaluator_agreement
# ---------------------------------------------------------------------------


def test_unanimous_chain_is_reported_as_agreement():
    interview_ratings = {
        f"interview_round_{i}": _round(
            f"Round {i}", ALL_FIVES, score=5.0, tier="highly_qualified", name=f"E{i}"
        )
        for i in (1, 2, 3)
    }

    read = evaluator_agreement(interview_ratings)

    assert read.unanimous is True
    assert read.submitted_rounds == 3
    assert "Highly Qualified" in read.summary
    assert not any(r.is_outlier for r in read.rounds)


def test_a_divergent_evaluator_is_named_along_with_the_category():
    """The Department Head rating Work Background well below the others is
    exactly the thing HR needs surfaced, and the thing the old screen
    could not say."""
    low_work = {**ALL_FIVES, "C1": 2, "C2": 2, "C3": 2}
    interview_ratings = {
        "interview_round_1": _round("HR", ALL_FIVES, score=5.0, tier="highly_qualified", name="Rosalie"),
        "interview_round_2": _round("Dept", low_work, score=4.18, tier="qualified", name="Armando"),
        "interview_round_3": _round("VP", ALL_FIVES, score=5.0, tier="highly_qualified", name="Teresita"),
    }

    read = evaluator_agreement(interview_ratings)

    assert read.unanimous is False
    assert "Armando" in read.summary
    assert "lower" in read.summary
    assert "Work Background" in read.summary
    assert [r.stage_type for r in read.rounds if r.is_outlier] == ["interview_round_2"]


def test_an_evaluator_rating_higher_than_the_rest_is_flagged_too():
    """Not only the pessimist. An outlier in either direction is worth
    HR's attention."""
    interview_ratings = {
        "interview_round_1": _round("HR", {k: 3 for k in ALL_FIVES}, score=3.0, tier="qualified", name="Rosalie"),
        "interview_round_2": _round("Dept", {k: 3 for k in ALL_FIVES}, score=3.0, tier="qualified", name="Armando"),
        "interview_round_3": _round("VP", ALL_FIVES, score=5.0, tier="highly_qualified", name="Teresita"),
    }

    read = evaluator_agreement(interview_ratings)

    assert "Teresita" in read.summary
    assert "higher" in read.summary


def test_a_single_evaluated_round_says_there_is_nothing_to_compare():
    interview_ratings = {
        "interview_round_1": _round("HR", ALL_FIVES, score=5.0, tier="highly_qualified", name="Rosalie"),
        "interview_round_2": {"label": "Dept", "item_ratings": None, "computed_score": None,
                              "tier": None, "recommendation": None, "assigned_evaluator_name": "Armando"},
    }

    read = evaluator_agreement(interview_ratings)

    assert read.submitted_rounds == 1
    assert read.unanimous is False
    assert "Rosalie" in read.summary
    assert "outstanding" in read.summary


def test_no_evaluations_yet_is_said_plainly():
    read = evaluator_agreement(
        {"interview_round_1": {"label": "HR", "item_ratings": None, "computed_score": None,
                               "tier": None, "recommendation": None, "assigned_evaluator_name": None}}
    )

    assert read.submitted_rounds == 0
    assert read.summary == "No interview round has been evaluated yet."


# ---------------------------------------------------------------------------
# band_label, match_reading, ordinal
# ---------------------------------------------------------------------------


def test_band_label_uses_the_forms_own_wording():
    assert band_label(5.0) == "Highly Qualified"
    assert band_label(4.0) == "Qualified"
    assert band_label(1.5) == "Not Qualified"


def test_match_reading_is_anchored_on_the_flag_threshold():
    """The wording and the behaviour must describe the same thing — a
    score the matcher flags has to read as flagged."""
    assert "flagged" in match_reading(MATCH_FLAG_THRESHOLD - 0.1)
    assert "flagged" not in match_reading(MATCH_FLAG_THRESHOLD)
    assert "strong" in match_reading(85.0).lower()
    assert match_reading(None).startswith("Not scored yet")


@pytest.mark.parametrize(
    "n,expected", [(1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (11, "11th"), (12, "12th"), (21, "21st")]
)
def test_ordinal(n, expected):
    assert ordinal(n) == expected


def test_a_uniformly_lower_evaluator_is_not_pinned_to_one_category():
    """An evaluator who marked every item a point below their colleagues
    diverges on all four categories equally. Naming whichever sorted
    first would invent a distinction their ratings do not make — and the
    Decision Brief Agent, handed that line, elaborates on it."""
    all_fours = {k: 4 for k in ALL_FIVES}
    interview_ratings = {
        "interview_round_1": _round("HR", ALL_FIVES, score=5.0, tier="highly_qualified", name="Rosalie"),
        "interview_round_2": _round("Dept", all_fours, score=4.0, tier="qualified", name="Armando"),
        "interview_round_3": _round("VP", ALL_FIVES, score=5.0, tier="highly_qualified", name="Teresita"),
    }

    summary = evaluator_agreement(interview_ratings).summary

    assert "Armando" in summary
    assert "across the rubric generally" in summary
    for label in ("Personal Background", "Educational Qualifications", "Work Background", "Job Expectations"):
        assert label not in summary


def test_one_clearly_divergent_category_is_still_named():
    """The margin rule must not suppress a real, isolated disagreement."""
    low_work_only = {**ALL_FIVES, "C1": 2, "C2": 2, "C3": 2}
    interview_ratings = {
        "interview_round_1": _round("HR", ALL_FIVES, score=5.0, tier="highly_qualified", name="Rosalie"),
        "interview_round_2": _round("Dept", low_work_only, score=4.18, tier="qualified", name="Armando"),
        "interview_round_3": _round("VP", ALL_FIVES, score=5.0, tier="highly_qualified", name="Teresita"),
    }

    assert "Work Background" in evaluator_agreement(interview_ratings).summary
