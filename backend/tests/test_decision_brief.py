"""Tests for the fact sheet the Decision Brief Agent is written from --
services/decision_brief.build_facts.

The agent itself is a single prompted call; what makes its output
trustworthy is that it can only see these lines. So the lines are what's
worth testing: anything false here becomes a false sentence in the
brief, and the verification run already showed the model elaborating
confidently on a distinction the facts asserted but the ratings didn't
contain.
"""

from app.domain.insights import aspect_scores, evaluator_agreement
from app.services.decision_brief import build_facts

ALL_FIVES = {
    "A1": 5, "A2": 5, "B1": 5, "B2": 5, "C1": 5, "C2": 5, "C3": 5,
    "D1": 5, "D2": 5, "D3": 5, "D4": 5,
}


def _round(label, ratings, *, score, tier, name):
    return {
        "label": label,
        "item_ratings": ratings,
        "computed_score": score,
        "tier": tier,
        "recommendation": "recommended",
        "assigned_evaluator_name": name,
    }


def _facts(interview_ratings, **kwargs):
    return build_facts(
        job_title=kwargs.get("job_title", "IT Systems Administrator"),
        match_score=kwargs.get("match_score"),
        match_gaps=kwargs.get("match_gaps", []),
        aspects=aspect_scores(interview_ratings),
        agreement=evaluator_agreement(interview_ratings),
        exam_score=kwargs.get("exam_score"),
        exam_rank=kwargs.get("exam_rank"),
        exam_cohort=kwargs.get("exam_cohort"),
    ).lines


def test_no_strongest_area_is_claimed_when_every_area_is_level():
    """Marco Villanueva's demo record: rated 5/4/5 flat across all eleven
    items, so all four categories average to exactly 4.67. The first
    version of this said "Strongest area: Personal Background", and the
    brief duly reported "particularly strong personal background scores"
    about a candidate whose four areas were identical."""
    ratings = {
        "interview_round_1": _round("HR", ALL_FIVES, score=5.0, tier="highly_qualified", name="Rosalie"),
        "interview_round_2": _round("Dept", {k: 4 for k in ALL_FIVES}, score=4.0, tier="qualified", name="Armando"),
        "interview_round_3": _round("VP", ALL_FIVES, score=5.0, tier="highly_qualified", name="Teresita"),
    }

    lines = _facts(ratings)

    assert not any(line.startswith("Strongest area") for line in lines)
    assert not any(line.startswith("Weakest area") for line in lines)
    assert any("rated evenly across all 4 areas" in line for line in lines)


def test_a_real_spread_reports_both_ends():
    ratings = {
        "interview_round_1": _round(
            "HR", {**ALL_FIVES, "C1": 2, "C2": 2, "C3": 2}, score=4.18, tier="qualified", name="Rosalie"
        ),
    }

    lines = _facts(ratings)

    assert any(line == "Strongest area: Personal Background at 5 of 5." for line in lines)
    assert any(line == "Weakest area: Work Background at 2 of 5." for line in lines)


def test_exam_standing_is_written_as_a_rank_when_there_is_a_cohort():
    lines = _facts({}, exam_score=88, exam_rank=1, exam_cohort=3)

    assert any("1st of 3 candidates" in line for line in lines)


def test_a_sole_candidate_is_not_told_they_ranked_first_of_one():
    lines = _facts({}, exam_score=88, exam_rank=1, exam_cohort=1)

    exam_line = next(line for line in lines if line.startswith("Examination score"))
    assert exam_line == "Examination score: 88 out of 100."


def test_the_fingerprint_tracks_the_facts_not_their_order_of_computation():
    """Staleness detection is a fingerprint comparison, so identical
    records must fingerprint identically and a changed one must not."""
    ratings = {"interview_round_1": _round("HR", ALL_FIVES, score=5.0, tier="highly_qualified", name="R")}
    kwargs = dict(match_score=78.8, exam_score=88, exam_rank=1, exam_cohort=3)

    a = build_facts(
        job_title="Job", match_gaps=[], aspects=aspect_scores(ratings),
        agreement=evaluator_agreement(ratings), **kwargs
    )
    b = build_facts(
        job_title="Job", match_gaps=[], aspects=aspect_scores(ratings),
        agreement=evaluator_agreement(ratings), **kwargs
    )
    assert a.fingerprint == b.fingerprint

    moved = build_facts(
        job_title="Job", match_gaps=[], aspects=aspect_scores(ratings),
        agreement=evaluator_agreement(ratings),
        match_score=78.8, exam_score=88, exam_rank=2, exam_cohort=3,
    )
    assert moved.fingerprint != a.fingerprint


def test_fact_rows_break_out_the_same_facts_the_model_is_given():
    """The screen lays the facts out from `rows`; the model and the
    fingerprint use `lines`. One row per line, each row's text *being*
    its line, so the two can never describe different records."""
    ratings = {
        "interview_round_1": _round("Round 1", ALL_FIVES, score=5.0, tier="highly_qualified", name="Ana Cruz"),
    }
    facts = build_facts(
        job_title="IT Systems Administrator",
        match_score=78.8,
        match_gaps=["Docker containers", "Nagios monitoring"],
        aspects=aspect_scores(ratings),
        agreement=evaluator_agreement(ratings),
        exam_score=88,
        exam_rank=1,
        exam_cohort=3,
    )

    assert [row.text for row in facts.rows] == facts.lines
    rows = {row.key: row for row in facts.rows}
    assert rows["skill_match"].value == "78.8 / 100"
    assert rows["requirement_gaps"].items == ["Docker containers", "Nagios monitoring"]
    assert [s.name for s in rows["rubric"].scores] == [
        "Personal Background",
        "Educational Qualifications",
        "Work Background",
        "Job Expectations",
    ]
    assert rows["exam"].value == "88 / 100"
    assert rows["exam"].note == "1st of 3 candidates who sat it for this job."
