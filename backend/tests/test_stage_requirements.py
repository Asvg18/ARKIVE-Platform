"""Rules for what each stage owes before it counts as done.

Companion to the DFA tests -- those check that a *move* is legal; these
check that the stage being left actually produced something.

Pure-function tests, deliberately -- domain.stage_requirements takes no
database, so every rule here is decidable from its arguments. The gap
these rules close was found on a real record: application 2 reached a
hire with its HR Administrator interview marked complete and no
scorecard behind it, and the DFA had nothing to say since sequence was
never violated.
"""

from app.domain.stage_requirements import missing_requirements


def labels(*args, **kwargs) -> list[str]:
    return [item.label for item in missing_requirements(*args, **kwargs)]


# --- Interviews -------------------------------------------------------


def test_an_interview_with_no_evaluation_is_outstanding():
    assert labels("interview_hr_director", {"schedule": {"date": "2026-08-01"}}) == [
        "Interview scorecard"
    ]


def test_scheduling_an_interview_is_not_conducting_one():
    """The exact shape that got through on application 2: a schedule and
    nothing else, marked complete."""
    assert labels("interview_vp", {"schedule": {"date": "x", "time": "y"}})


def test_a_submitted_evaluation_satisfies_the_round():
    assert labels("interview_round_2", {"evaluation": {"submitted_at": "2026-08-30T00:00:00"}}) == []


def test_a_legacy_evaluation_without_a_computed_score_still_counts():
    """Pre-redesign evaluations carry submitted_at and no computed_score.
    A real evaluator submitted them; calling them outstanding would put
    words in that person's mouth."""
    evaluation = {"submitted_at": "2026-07-30T00:00:00", "rating": 4, "notes": "Good"}
    assert labels("interview_dept_head", {"evaluation": evaluation}) == []


def test_an_evaluation_that_was_never_submitted_does_not_count():
    """A draft is not a submission."""
    assert labels("interview_round_1", {"evaluation": {"rating": 5, "submitted_at": None}})


def test_every_interview_slot_is_covered_by_the_same_rule():
    """Legacy named rounds and generic interview_round_k alike — the rule
    keys off the shared prefix, so a new slot needs no change here."""
    for stage in (
        "interview_hr_director",
        "interview_dept_head",
        "interview_vp",
        "interview_round_1",
        "interview_round_6",
    ):
        assert labels(stage, {}) == ["Interview scorecard"], stage


# --- Examinations -----------------------------------------------------


def test_booking_an_exam_is_not_sitting_one():
    assert labels("examination", {"schedule": {"date": "2026-08-05"}}) == ["Examination score"]


def test_a_recorded_score_satisfies_an_exam():
    assert labels("examination", {"schedule": {}, "score": 92.0}) == []


def test_a_zero_score_is_a_score():
    """Falsy but recorded. Someone genuinely scored zero, and treating
    that as 'not yet examined' would erase a real result."""
    assert labels("examination_2", {"score": 0}) == []


# --- The rest ---------------------------------------------------------


def test_skill_matching_needs_a_score():
    assert labels("skill_matching", {"answers": []}) == ["Match score"]
    assert labels("skill_matching", {"match_score": 78.8}) == []


def test_document_upload_reads_the_resume_table_not_the_payload():
    """The resume is a row in application_resumes, not JSON. A filename
    written into the payload with no file behind it is exactly the
    inconsistency this rule exists to catch."""
    assert labels("document_upload", {"resume_filename": "cv.pdf"}, has_resume=False) == ["Resume"]
    assert labels("document_upload", {}, has_resume=True) == []


def test_not_looking_for_a_resume_is_not_the_same_as_not_finding_one():
    """has_resume=None means the caller did not check. Withhold the
    opinion rather than reporting a gap nobody looked for."""
    assert labels("document_upload", {}, has_resume=None) == []


def test_final_decision_needs_a_recorded_decision():
    assert labels("final_decision", {}) == ["Final decision"]
    assert labels("final_decision", {"decisions": [{"status": "hired"}]}) == []


def test_onboarding_is_terminal_and_owes_nothing():
    assert labels("onboarding", None) == []


def test_an_unknown_stage_withholds_its_opinion():
    """The enum will grow. A rule invented for a stage this module has
    never been taught about is worse than no rule."""
    assert labels("some_future_stage", None) == []


def test_a_missing_requirement_carries_enough_to_render():
    """The client renders these as a checklist, the same way the hire
    gate's blockers already are."""
    (item,) = missing_requirements("final_decision", None)
    assert item.key and item.label and item.detail
