"""Tests for the consolidated Decision Support synthesis -- services/
synthesis.py and the `synthesis` block it puts on CandidateProfile and
the Pre-201 package.

Motivating defect: both hired applicants in the dev database showed a
blank final synthesis score with no explanation of what was missing or
whether it could ever arrive. final_synthesis_score stays all-or-nothing
here -- that part is correct -- so these tests are about the
*explanation* alongside it, and about the AgentRun log finally being
read back by something."""

import json

import pytest

from sqlalchemy import select

from app.domain.decision_support import compute_final_synthesis_score
from app.models.agent_run import AgentRun
from app.models.enums import StageType, UserRole
from app.models.stage_instance import StageInstance
from app.services.applications import create_application_with_stage_instances
from tests.conftest import MOCK_BRIEF_RATIONALE, MOCK_BRIEF_VERDICT, MOCK_RUBRIC_SCORE, auth_headers
from tests.test_applicant_flow import _RESUME_DATA, _SAMPLE_RESUME_PDF
from tests.test_decision_support import FULL_WORKFLOW, _advance_to, _assign_and_submit

# no skill_matching or examination stage -- the shape the demo seed's
# "Library Assistant" job uses. those two criteria carry 60.6% of the
# WSM's weight, so this workflow can never produce a final synthesis
# score at all -- the synthesis block has to say so, not show an
# unexplained dash.
NO_SCREENING_WORKFLOW = [
    "document_upload",
    "interview_round_1",
    "interview_round_2",
    "final_decision",
]


def _criteria_by_key(synthesis: dict) -> dict[str, dict]:
    return {c["key"]: c for c in synthesis["criteria"]}


def _agents_by_name(synthesis: dict) -> dict[str, dict]:
    return {a["agent_name"]: a for a in synthesis["agents"]}


def _set_match_score(db_session, application, score: float) -> None:
    """Inject Skill Matching Agent output directly onto the already-
    complete skill_matching StageInstance — same precedent as
    test_decision_support.test_exam_percentile_and_final_synthesis_score;
    running the real RAG agent is out of scope for these tests."""
    instance = (
        db_session.query(StageInstance)
        .filter(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.skill_matching,
        )
        .one()
    )
    instance.payload = {**(instance.payload or {}), "match_score": score}
    db_session.commit()


def test_synthesis_explains_a_blocked_score_when_data_is_merely_pending(
    client, db_session, make_job, make_application, hr_admin
):
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    _advance_to(client, application, "skill_matching", hr_headers, FULL_WORKFLOW)
    _set_match_score(db_session, application, 71.8)

    synthesis = client.get(
        f"/hr/applications/{application.id}/profile", headers=hr_headers
    ).json()["synthesis"]

    assert synthesis["final_synthesis_score"] is None
    # Every criterion is reachable for this workflow — the three that are
    # absent are absent because nobody has recorded them yet.
    assert synthesis["criteria_applicable"] == 4
    assert synthesis["criteria_available"] == 1

    criteria = _criteria_by_key(synthesis)
    assert criteria["skill_match"]["status"] == "available"
    assert criteria["skill_match"]["display_value"] == "71.8%"
    assert criteria["skill_match"]["contribution"] == round(71.8 * 0.569, 2)
    for key in ("exam_percentile", "executive_consensus", "interview_rubric"):
        assert criteria[key]["status"] == "missing"
        assert criteria[key]["contribution"] is None

    assert synthesis["blocked_reason"].startswith("Awaiting")
    assert "Examination Percentile" in synthesis["blocked_reason"]
    assert "never treated as zero" in synthesis["blocked_reason"]


def test_synthesis_flags_criteria_this_workflow_can_never_produce(
    client, db_session, make_job, make_application, hr_admin
):
    job = make_job(NO_SCREENING_WORKFLOW, title="No-Screening Job")
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    synthesis = client.get(
        f"/hr/applications/{application.id}/profile", headers=hr_headers
    ).json()["synthesis"]

    criteria = _criteria_by_key(synthesis)
    # The distinction this whole design exists for: "no such stage in
    # this workflow" is a different fact from "not recorded yet", and the
    # two used to be indistinguishable (both rendered as a bare dash).
    assert criteria["skill_match"]["status"] == "not_applicable"
    assert criteria["exam_percentile"]["status"] == "not_applicable"
    assert criteria["executive_consensus"]["status"] == "missing"
    assert criteria["interview_rubric"]["status"] == "missing"
    assert synthesis["criteria_applicable"] == 2
    assert synthesis["criteria_total"] == 4

    assert "not reachable for this requisition" in synthesis["blocked_reason"]
    # The weight is quoted so HR can see how much of the score is being
    # forfeited by this workflow shape, not just that something is off.
    assert "56.9%" in synthesis["blocked_reason"]


def test_synthesis_contributions_sum_to_the_final_score(
    client, db_session, make_job, make_application, hr_admin, evaluator, make_user
):
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    other_applicant = make_user("synth-other@arkivetesting.com", UserRole.applicant)
    other_application = create_application_with_stage_instances(
        db_session, applicant_id=other_applicant.id, requisition=job
    )
    db_session.flush()

    _advance_to(client, application, "examination", hr_headers, FULL_WORKFLOW)
    _advance_to(client, other_application, "examination", hr_headers, FULL_WORKFLOW)
    for target, score in ((application, 90), (other_application, 60)):
        resp = client.patch(
            f"/hr/applications/{target.id}/examination-result",
            json={"stage_type": "examination", "score": score},
            headers=hr_headers,
        )
        assert resp.status_code == 200, resp.text

    _set_match_score(db_session, application, 80.0)

    dept_evaluator = make_user("synth-dept@arkivetesting.com", evaluator.role)
    vp_evaluator = make_user("synth-vp@arkivetesting.com", evaluator.role)
    _advance_to(client, application, "interview_round_3", hr_headers, FULL_WORKFLOW)
    _assign_and_submit(client, db_session, job, application, evaluator, hr_headers, "interview_round_1", 5)
    _assign_and_submit(client, db_session, job, application, dept_evaluator, hr_headers, "interview_round_2", 4)
    _assign_and_submit(client, db_session, job, application, vp_evaluator, hr_headers, "interview_round_3", 3)

    synthesis = client.get(
        f"/hr/applications/{application.id}/profile", headers=hr_headers
    ).json()["synthesis"]

    expected = compute_final_synthesis_score(
        skill_score=80.0,
        exam_percentile=75.0,
        executive_consensus_score=3.9 * 20,
        interview_rubric_score=MOCK_RUBRIC_SCORE,
    )
    assert synthesis["final_synthesis_score"] == expected
    assert synthesis["blocked_reason"] is None
    assert synthesis["criteria_available"] == 4

    criteria = _criteria_by_key(synthesis)
    # C3 is stored on the scorecard's native 1-5 scale but fed to the WSM
    # normalized to 0-100 — the breakdown has to show both, or the 78.0
    # that actually enters the formula looks unrelated to the 3.90 HR saw.
    assert criteria["executive_consensus"]["display_value"] == "3.90 / 5"
    assert criteria["executive_consensus"]["value"] == 78.0

    # Each contribution is rounded independently, so their sum can differ
    # from the independently-rounded total by a couple of hundredths.
    total = sum(c["contribution"] for c in synthesis["criteria"])
    assert total == pytest.approx(expected, abs=0.05)


def test_agent_trail_reports_which_agents_ran(
    client, db_session, make_job, make_application, hr_admin, evaluator
):
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    _advance_to(client, application, "interview_round_1", hr_headers, FULL_WORKFLOW)
    _assign_and_submit(client, db_session, job, application, evaluator, hr_headers, "interview_round_1", 4)

    synthesis = client.get(
        f"/hr/applications/{application.id}/profile", headers=hr_headers
    ).json()["synthesis"]

    agents = _agents_by_name(synthesis)
    # Submitting one scorecard fires three agents: the deterministic
    # scorecard computation, the LLM rubric-coverage read, and the
    # Decision Brief written from the newly-complete facts.
    assert agents["evaluator_scorecard_agent"]["status"] == "ran"
    assert agents["interview_synthesis_agent"]["status"] == "ran"
    assert agents["decision_brief_agent"]["status"] == "ran"
    assert agents["evaluator_scorecard_agent"]["last_run_at"] is not None
    # Applicable to this workflow, but nothing has triggered it.
    assert agents["matching_agent"]["status"] == "pending"
    assert agents["matching_agent"]["run_count"] == 0
    # Decision Support is a pure function recomputed on every read — it
    # has no run event, and claiming one would be false bookkeeping.
    assert agents["decision_support_agent"]["status"] == "derived"
    assert agents["decision_support_agent"]["kind"] == "derived"

    trail = synthesis["agent_trail"]
    assert len(trail) == 3
    assert {entry["agent_name"] for entry in trail} == {
        "evaluator_scorecard_agent",
        "interview_synthesis_agent",
        "decision_brief_agent",
    }
    assert all(entry["triggered_by_stage"] == "interview_round_1" for entry in trail)
    assert all(entry["triggered_by_stage_label"] == "Interview Round 1" for entry in trail)


def test_agent_coverage_marks_agents_whose_stage_the_workflow_lacks(
    client, db_session, make_job, make_application, hr_admin
):
    """A short workflow must not read as five agents having failed."""
    job = make_job(NO_SCREENING_WORKFLOW, title="Coverage Job")
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    agents = _agents_by_name(
        client.get(f"/hr/applications/{application.id}/profile", headers=hr_headers).json()[
            "synthesis"
        ]
    )
    for name in ("matching_agent", "interview_analysis_agent", "exam_scheduling_agent"):
        assert agents[name]["status"] == "not_applicable", name
    assert agents["evaluator_scorecard_agent"]["status"] == "pending"
    assert agents["document_parsing_agent"]["status"] == "pending"


def test_pre_201_package_carries_the_synthesis(
    client, db_session, make_job, make_application, hr_admin
):
    """The hired applicant's permanent record has to state which criteria
    actually backed the decision — this is exactly the case that produced
    two blank, unexplained hired records in the dev database."""
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    # This test hires a completely empty record on purpose — that is the
    # case it exists to cover. Post-hire-gate that needs the explicit
    # acknowledgement, which is exactly the honest outcome: the record is
    # hollow, and now something says so.
    resp = client.patch(
        f"/hr/applications/{application.id}/status",
        json={"status": "hired", "acknowledged_incomplete": True, "reason": "Seeded fixture — record intentionally empty."},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text

    package = client.get(
        f"/hr/applications/{application.id}/pre-201-package", headers=hr_headers
    ).json()

    assert package["final_synthesis_score"] is None
    synthesis = package["synthesis"]
    assert synthesis["criteria_available"] == 0
    assert synthesis["blocked_reason"] is not None
    # The record states all four criteria were absent rather than simply
    # omitting them.
    assert len(synthesis["criteria"]) == 4
    assert all(c["status"] == "missing" for c in synthesis["criteria"])


def test_document_parsing_agent_run_is_logged_on_upload(
    client, applicant, hr_admin, make_job
):
    """The Document Parsing Agent used to leave no trace at all — the
    architecture claims four agents, but only three ever wrote to the
    AgentRun log. Its output of record is the ApplicationResume created
    at document_upload, so that is where the run is logged."""
    job = make_job(["document_upload", "skill_matching", "final_decision"])
    headers = auth_headers(client, applicant.email)
    application_id = client.post(
        "/applications", json={"requisition_id": job.id}, headers=headers
    ).json()["id"]

    with open(_SAMPLE_RESUME_PDF, "rb") as f:
        resp = client.post(
            f"/applicant/applications/{application_id}/document-upload",
            headers=headers,
            files={"resume_file": ("resume.pdf", f, "application/pdf")},
            data={"resume_data": json.dumps(_RESUME_DATA)},
        )
    assert resp.status_code == 200, resp.text

    hr_headers = auth_headers(client, hr_admin.email)
    synthesis = client.get(
        f"/hr/applications/{application_id}/profile", headers=hr_headers
    ).json()["synthesis"]

    agents = _agents_by_name(synthesis)
    assert agents["document_parsing_agent"]["status"] == "ran"
    assert agents["document_parsing_agent"]["run_count"] == 1

    entry = next(
        e for e in synthesis["agent_trail"] if e["agent_name"] == "document_parsing_agent"
    )
    assert entry["label"] == "Document Parsing Agent"
    assert entry["triggered_by_stage_label"] == "Document Upload"


# ---------------------------------------------------------------------------
# The decision-brief half of the synthesis (2026-08-31) — the sections HR
# actually reads, as opposed to the weighting the score was derived from.
# ---------------------------------------------------------------------------


def test_aspects_roll_the_rubric_up_by_category(
    client, db_session, make_job, make_application, hr_admin, make_user
):
    """The eleven item ratings per round have always been stored and only
    ever rendered raw. This is the roll-up that answers "which areas is
    this candidate strong in"."""
    job = make_job(FULL_WORKFLOW, title="Aspect Job")
    application = make_application(job)
    evaluator = make_user("aspect-eval@arkivetesting.com", UserRole.evaluator)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    _advance_to(client, application, "interview_round_1", hr_headers, FULL_WORKFLOW)
    _assign_and_submit(
        client, db_session, job, application, evaluator, hr_headers, "interview_round_1", 4
    )

    synthesis = client.get(
        f"/hr/applications/{application.id}/profile", headers=hr_headers
    ).json()["synthesis"]

    aspects = {a["code"]: a for a in synthesis["aspects"]}
    assert set(aspects) == {"A", "B", "C", "D"}
    # _assign_and_submit rates every item the same, so every category
    # averages to it — the point here is that all four are reported on
    # the form's own 1-5 scale, not rescaled to 0-100.
    assert all(a["mean"] == 4.0 for a in aspects.values())
    assert aspects["C"]["label"] == "Work Background"
    assert aspects["C"]["items_rated"] == 3
    assert aspects["A"]["band"] == "Qualified"


def test_a_disputed_requirement_keeps_hr_wording_apart_from_the_note(
    client, db_session, make_job, make_application, hr_admin
):
    """The requirement is HR's text and the note carries the AI's
    reasoning, so they travel as two fields: the screen tidies the note's
    long dashes for display (revisions 2.0, phase 3), and HR's wording,
    any dash it typed included, reaches the screen as written."""
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    _advance_to(client, application, "skill_matching", hr_headers, FULL_WORKFLOW)

    typed_by_hr = "Bachelor's degree — Computer Science or a related field"
    note = "Disputed: judged not met twice, but the resume closely matches it. Check the resume."
    instance = (
        db_session.query(StageInstance)
        .filter(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.skill_matching,
        )
        .one()
    )
    instance.payload = {
        **(instance.payload or {}),
        "match_score": 72.0,
        "requirement_checks": [
            {"requirement": typed_by_hr, "verdict": "not_met", "evidence_quote": "", "verified": False, "note": note},
            {"requirement": "Two years of teaching", "verdict": "met", "evidence_quote": "taught", "verified": True, "note": ""},
        ],
    }
    db_session.commit()

    evidence = client.get(
        f"/hr/applications/{application.id}/profile", headers=hr_headers
    ).json()["synthesis"]["evidence"]

    assert evidence["match_disputed"] == [{"requirement": typed_by_hr, "note": note}]


def test_the_brief_is_written_on_submission_and_carries_its_own_facts(
    client, db_session, make_job, make_application, hr_admin, make_user
):
    job = make_job(FULL_WORKFLOW, title="Brief Job")
    application = make_application(job)
    evaluator = make_user("brief-eval@arkivetesting.com", UserRole.evaluator)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    _advance_to(client, application, "interview_round_1", hr_headers, FULL_WORKFLOW)
    _assign_and_submit(
        client, db_session, job, application, evaluator, hr_headers, "interview_round_1", 4
    )

    synthesis = client.get(
        f"/hr/applications/{application.id}/profile", headers=hr_headers
    ).json()["synthesis"]

    assert synthesis["brief"]["verdict"] == MOCK_BRIEF_VERDICT
    assert synthesis["brief"]["rationale"] == MOCK_BRIEF_RATIONALE
    # Freshly written, so it describes the record as it currently stands.
    assert synthesis["brief"]["stale"] is False
    # The facts it was written from are the facts on screen, so every
    # sentence is checkable against a number HR can see.
    assert synthesis["brief"]["facts"] == synthesis["fact_sheet"]
    assert any("Work Background" in line for line in synthesis["fact_sheet"])


def test_a_brief_written_against_an_older_record_is_reported_stale(
    client, db_session, make_job, make_application, hr_admin, make_user
):
    """A sibling candidate's exam score can move this candidate's
    standing without touching their own record. The brief must say it is
    out of date rather than quietly describing the older version."""
    job = make_job(FULL_WORKFLOW, title="Stale Brief Job")
    application = make_application(job)
    evaluator = make_user("stale-eval@arkivetesting.com", UserRole.evaluator)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    _advance_to(client, application, "interview_round_1", hr_headers, FULL_WORKFLOW)
    _assign_and_submit(
        client, db_session, job, application, evaluator, hr_headers, "interview_round_1", 4
    )

    run = db_session.scalars(
        select(AgentRun).where(
            AgentRun.application_id == application.id,
            AgentRun.agent_name == "decision_brief_agent",
        )
    ).first()
    run.output = {**run.output, "fingerprint": "definitely-not-current"}
    db_session.flush()

    synthesis = client.get(
        f"/hr/applications/{application.id}/profile", headers=hr_headers
    ).json()["synthesis"]

    assert synthesis["brief"]["stale"] is True
    # Still shown, not withheld — a stale justification is more useful
    # than none, provided it is labelled.
    assert synthesis["brief"]["verdict"] == MOCK_BRIEF_VERDICT


def test_reading_the_profile_never_calls_the_brief_agent(
    client, db_session, make_job, make_application, hr_admin, make_user, mock_ai_agents
):
    """The Candidate Profile is on the eight-second live-refresh poll. A
    model call in the read path would mean one OpenAI request per open
    tab per eight seconds."""
    from app.services import decision_brief

    job = make_job(FULL_WORKFLOW, title="Poll Job")
    application = make_application(job)
    evaluator = make_user("poll-eval@arkivetesting.com", UserRole.evaluator)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    _advance_to(client, application, "interview_round_1", hr_headers, FULL_WORKFLOW)
    _assign_and_submit(
        client, db_session, job, application, evaluator, hr_headers, "interview_round_1", 4
    )

    invoke = decision_brief.ChatOpenAI.return_value.with_structured_output.return_value.invoke
    calls_after_write = invoke.call_count
    assert calls_after_write == 1, "the brief should be written exactly once, on submission"

    for _ in range(5):
        client.get(f"/hr/applications/{application.id}/profile", headers=hr_headers)

    assert invoke.call_count == calls_after_write


def test_a_malformed_brief_row_degrades_instead_of_breaking_the_profile(
    client, db_session, make_job, make_application, hr_admin, make_user
):
    """AgentRun is an append-only log of whatever an agent produced. One
    row in an older shape must not take down the whole Candidate
    Profile."""
    job = make_job(FULL_WORKFLOW, title="Malformed Brief Job")
    application = make_application(job)
    evaluator = make_user("malformed-eval@arkivetesting.com", UserRole.evaluator)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    _advance_to(client, application, "interview_round_1", hr_headers, FULL_WORKFLOW)
    _assign_and_submit(
        client, db_session, job, application, evaluator, hr_headers, "interview_round_1", 4
    )

    run = db_session.scalars(
        select(AgentRun).where(
            AgentRun.application_id == application.id,
            AgentRun.agent_name == "decision_brief_agent",
        )
    ).first()
    run.output = {"something": "from an older shape"}
    db_session.flush()

    resp = client.get(f"/hr/applications/{application.id}/profile", headers=hr_headers)

    assert resp.status_code == 200
    assert resp.json()["synthesis"]["brief"] is None


def _agreement(recommendations: list[str | None], *, unanimous: bool = True, total: int | None = None):
    from app.schemas.synthesis import AgreementRead, RoundRead

    rounds = [
        RoundRead(
            stage_type=f"interview_round_{i + 1}",
            label=f"Round {i + 1}",
            evaluator_name=None,
            score=4.0,
            tier="qualified",
            tier_label="Qualified",
            recommendation=rec,
            is_outlier=False,
        )
        for i, rec in enumerate(recommendations)
    ]
    return AgreementRead(
        submitted_rounds=len(rounds),
        total_rounds=total if total is not None else len(rounds),
        unanimous=unanimous,
        summary="The chain's own summary.",
        rounds=rounds,
    )


def _signals(**overrides) -> dict[str, dict]:
    from app.services.synthesis import _headline

    kwargs = dict(
        overall_tier="qualified",
        final_synthesis_score=80.0,
        agreement=_agreement([None, None, None]),
        exam_score=None,
        exam_rank=None,
        exam_cohort=None,
        match_gaps=[],
    )
    kwargs.update(overrides)
    return {s.key: s.model_dump() for s in _headline(**kwargs).signals}


def test_headline_signals_say_which_way_each_fact_points():
    """The verdict card's facts used to be identical grey chips, so the
    gap and the good news looked alike. Each now carries a tone."""
    signals = _signals(
        exam_score=88.0,
        exam_rank=1,
        exam_cohort=3,
        match_gaps=["Cataloguing experience", "MARC21", "Koha"],
    )

    assert signals["evaluators"]["label"] == "3 of 3 rounds evaluated"
    assert signals["evaluators"]["tone"] == "positive"
    assert signals["evaluators"]["detail"] == "The chain's own summary."

    assert signals["exam_rank"]["label"] == "1st of 3 on the exam"
    assert signals["exam_rank"]["tone"] == "positive"
    assert signals["exam_rank"]["detail"].startswith("Scored 88 / 100")

    gaps = signals["requirement_gaps"]
    assert gaps["label"] == "3 unaddressed requirements"
    assert gaps["tone"] == "attention"
    assert gaps["items"] == ["Cataloguing experience", "MARC21", "Koha"]


@pytest.mark.parametrize(
    ("rank", "cohort", "tone"),
    [(1, 2, "positive"), (2, 2, "attention"), (2, 3, "neutral"), (3, 3, "attention"), (2, 10, "positive")],
)
def test_exam_rank_tone_follows_the_place_in_the_cohort(rank, cohort, tone):
    assert _signals(exam_rank=rank, exam_cohort=cohort)["exam_rank"]["tone"] == tone


@pytest.mark.parametrize(
    ("recommendations", "label", "tone"),
    [
        (["recommended", "highly_recommended"], "2 of 2 evaluators recommend", "positive"),
        (["recommended", "recommended", "not_recommended"], "2 of 3 evaluators recommend", "neutral"),
        (["recommended", "not_recommended", "not_recommended"], "1 of 3 evaluators recommend", "attention"),
    ],
)
def test_evaluator_signal_tone_follows_the_recommendations(recommendations, label, tone):
    signal = _signals(agreement=_agreement(recommendations))["evaluators"]
    assert (signal["label"], signal["tone"]) == (label, tone)


def test_a_split_chain_wants_a_look_but_an_unfinished_one_is_routine():
    split = _signals(agreement=_agreement([None, None], unanimous=False))["evaluators"]
    unfinished = _signals(agreement=_agreement([None], unanimous=False, total=3))["evaluators"]

    assert split["tone"] == "attention"
    assert (unfinished["label"], unfinished["tone"]) == ("1 of 3 rounds evaluated", "neutral")
