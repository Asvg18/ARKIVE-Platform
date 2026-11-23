"""Tests for the Decision Support agent -- the pure scoring formulas in
domain.decision_support, the real Interview Synthesis Agent, and the
aggregate fields it feeds on the HR Candidate Profile (evaluator_
consensus_score's 30/30/40 weighting, interview_rubric_score,
exam_percentile, overall_tier, final_synthesis_score). No prior
coverage existed for any of this."""

import openai
import pytest

from app.domain.decision_support import (
    compute_final_synthesis_score,
    compute_percentile_rank,
    compute_weighted_consensus,
)
from app.domain.scorecard import SCORECARD_ITEM_CODES
from app.models.agent_run import AgentRun
from app.models.enums import StageType, UserRole
from app.models.stage_instance import StageInstance
from app.schemas.interview_synthesis import InterviewSynthesisResult
from app.services.applications import create_application_with_stage_instances
from app.services.interview_synthesis import (
    AIExtractionFailedError,
    ExtractionNotConfiguredError,
    run_interview_synthesis,
)
from tests.conftest import MOCK_RUBRIC_SCORE, auth_headers, give_confirmed_time

WORKFLOW = ["document_upload", "skill_matching", "interview_round_1", "final_decision"]
FULL_WORKFLOW = [
    "document_upload",
    "skill_matching",
    "examination",
    "interview_round_1",
    "interview_round_2",
    "interview_round_3",
    "final_decision",
]


class _FakeOpenAIError(openai.OpenAIError):
    """A minimal openai.OpenAIError subclass, so tests don't need to
    reverse-engineer the real constructor signatures of APIError/
    APIConnectionError/etc. just to prove the except clause fires."""


def _all_items(rating: int | None) -> dict[str, int | None]:
    return {code: rating for code in SCORECARD_ITEM_CODES}


def _advance_to(client, application, target_stage, headers, workflow):
    """Fast-forwards to `target_stage` for setup, acknowledging that the
    stages walked past have recorded nothing.

    Not boilerplate -- these tests are about what happens *at* the
    target stage, so the rounds before it are deliberately hollow, and
    the sufficiency gate is right to stop them. acknowledged_incomplete
    is the same escape hatch HR uses; the stages land as `skipped`
    rather than pretending to be complete."""
    for stage in workflow[workflow.index(application.current_stage.value) + 1 : workflow.index(target_stage) + 1]:
        resp = client.post(
            f"/applications/{application.id}/transition",
            json={
                "target_stage": stage,
                "acknowledged_incomplete": True,
                "reason": "Test setup: fast-forwarding to the stage under test.",
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text


def _assign_and_submit(client, db_session, job, application, evaluator_user, headers, stage_type,
                       rating, recommendation="recommended"):
    from app.models.requisition_evaluator import RequisitionEvaluator

    db_session.add(RequisitionEvaluator(requisition_id=job.id, evaluator_id=evaluator_user.id))
    db_session.flush()
    resp = client.post(
        f"/hr/applications/{application.id}/interview-assignment",
        json={"stage_type": stage_type, "evaluator_id": evaluator_user.id},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    eval_headers = auth_headers(client, evaluator_user.email)
    resp = client.get("/evaluator/interviews", headers=eval_headers)
    stage_instance_id = next(i["stage_instance_id"] for i in resp.json() if i["application_id"] == application.id)
    give_confirmed_time(db_session, stage_instance_id)
    resp = client.post(
        f"/evaluator/interviews/{stage_instance_id}/evaluate",
        json={
            "item_ratings": _all_items(rating),
            "remarks": f"{stage_type} evaluation.",
            "recommendation": recommendation,
        },
        headers=eval_headers,
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Pure functions — core/decision_support.py, no DB, no mocking.
# ---------------------------------------------------------------------------


def test_compute_weighted_consensus_applies_institutional_weights():
    # 0.30*5 + 0.30*3 + 0.40*1 = 2.8 -- deliberately distinct from the
    # equal-weighted mean (3.0), proving this is a real weighted formula
    assert compute_weighted_consensus(hr_score=5, dept_score=3, vp_score=1) == 2.8


def test_compute_percentile_rank_no_ties():
    # score=90 among [90, 60]: 1 strictly below, 1 tied (itself) -> (1+0.5)/2*100.
    assert compute_percentile_rank(90, [90, 60]) == 75.0


def test_compute_percentile_rank_all_tied():
    # Every candidate scored the same -> the "no discriminating signal"
    # case lands everyone at the midpoint, 50.0.
    assert compute_percentile_rank(70, [70, 70, 70]) == 50.0


def test_compute_final_synthesis_score_exact_weights():
    result = compute_final_synthesis_score(
        skill_score=80.0, exam_percentile=75.0, executive_consensus_score=78.0, interview_rubric_score=72.5
    )
    expected = round(80.0 * 0.569 + 75.0 * 0.037 + 78.0 * 0.043 + 72.5 * 0.351, 2)
    assert result == expected


# ---------------------------------------------------------------------------
# run_interview_synthesis — DB fixtures + the autouse conftest mock.
# ---------------------------------------------------------------------------


def test_run_interview_synthesis_success_logs_agent_run(
    db_session, make_job, make_application, mock_ai_agents
):
    mock_ai_agents.return_value.with_structured_output.return_value.invoke.return_value = InterviewSynthesisResult(
        rubric_coverage_score=88.0, summary="Thorough, specific documentation."
    )
    job = make_job(WORKFLOW)
    application = make_application(job)

    result = run_interview_synthesis(
        db_session,
        application_id=application.id,
        stage_type="interview_round_1",
        item_ratings=_all_items(4),
        remarks="Solid answers across the board.",
    )

    assert result.rubric_coverage_score == 88.0
    db_session.flush()
    run = db_session.query(AgentRun).filter(AgentRun.application_id == application.id).one()
    assert run.agent_name == "interview_synthesis_agent"
    assert run.triggered_by_stage == "interview_round_1"
    assert run.output["rubric_coverage_score"] == 88.0


def test_run_interview_synthesis_raises_when_not_configured(
    db_session, make_job, make_application, monkeypatch
):
    from app.infra.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "")
    job = make_job(WORKFLOW)
    application = make_application(job)

    with pytest.raises(ExtractionNotConfiguredError):
        run_interview_synthesis(
            db_session,
            application_id=application.id,
            stage_type="interview_round_1",
            item_ratings=_all_items(3),
            remarks="x",
        )


def test_run_interview_synthesis_raises_ai_extraction_failed_on_generation_error(
    db_session, make_job, make_application, mock_ai_agents
):
    mock_ai_agents.return_value.with_structured_output.return_value.invoke.side_effect = _FakeOpenAIError("boom")
    job = make_job(WORKFLOW)
    application = make_application(job)

    with pytest.raises(AIExtractionFailedError):
        run_interview_synthesis(
            db_session,
            application_id=application.id,
            stage_type="interview_round_1",
            item_ratings=_all_items(3),
            remarks="x",
        )


# ---------------------------------------------------------------------------
# Aggregate profile fields — full pipeline through the real endpoints.
# ---------------------------------------------------------------------------


def test_evaluator_consensus_uses_weighted_formula_for_three_fixed_rounds(
    client, db_session, make_job, make_application, hr_admin, evaluator, make_user
):
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    dept_evaluator = make_user("dept-test@arkivetesting.com", evaluator.role)
    vp_evaluator = make_user("vp-test@arkivetesting.com", evaluator.role)

    _advance_to(client, application, "interview_round_3", hr_headers, FULL_WORKFLOW)
    _assign_and_submit(client, db_session, job, application, evaluator, hr_headers, "interview_round_1", 5)
    _assign_and_submit(client, db_session, job, application, dept_evaluator, hr_headers, "interview_round_2", 3)
    _assign_and_submit(client, db_session, job, application, vp_evaluator, hr_headers, "interview_round_3", 1)

    profile = client.get(f"/hr/applications/{application.id}/profile", headers=hr_headers).json()
    # 0.30*5 + 0.30*3 + 0.40*1 = 2.8 — not the equal-weighted 3.0, proving
    # the 30/30/40 formula actually ran instead of the old fallback mean.
    assert profile["evaluator_consensus_score"] == 2.8
    assert profile["overall_tier"] == "not_qualified"
    # all 3 rounds get the same mocked rubric_coverage_score, so the
    # weighted aggregation collapses to that value regardless of
    # weighting -- still proves the same consolidation path runs for C4
    assert profile["interview_rubric_score"] == MOCK_RUBRIC_SCORE


def test_exam_percentile_and_final_synthesis_score(
    client, db_session, make_job, make_application, hr_admin, evaluator, make_user
):
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    # A second candidate purely so this candidate's percentile math is
    # non-trivial (a single-candidate job would always rank at 100%).
    other_applicant = make_user("other-applicant@arkivetesting.com", UserRole.applicant)
    other_application = create_application_with_stage_instances(
        db_session, applicant_id=other_applicant.id, requisition=job
    )
    db_session.flush()

    _advance_to(client, application, "examination", hr_headers, FULL_WORKFLOW)
    _advance_to(client, other_application, "examination", hr_headers, FULL_WORKFLOW)

    resp = client.patch(
        f"/hr/applications/{application.id}/examination-result",
        json={"stage_type": "examination", "score": 90},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text
    resp = client.patch(
        f"/hr/applications/{other_application.id}/examination-result",
        json={"stage_type": "examination", "score": 60},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text

    # Skill Matching output is out of scope here -- injected directly on
    # the already-complete skill_matching StageInstance, same precedent
    # as test_interview_analysis.py's own profile-join test
    skill_instance = (
        db_session.query(StageInstance)
        .filter(StageInstance.application_id == application.id, StageInstance.stage_type == StageType.skill_matching)
        .one()
    )
    skill_instance.payload = {**(skill_instance.payload or {}), "match_score": 80.0}
    db_session.commit()

    dept_evaluator = make_user("dept2-test@arkivetesting.com", evaluator.role)
    vp_evaluator = make_user("vp2-test@arkivetesting.com", evaluator.role)
    _advance_to(client, application, "interview_round_3", hr_headers, FULL_WORKFLOW)
    _assign_and_submit(client, db_session, job, application, evaluator, hr_headers, "interview_round_1", 5)
    _assign_and_submit(client, db_session, job, application, dept_evaluator, hr_headers, "interview_round_2", 4)
    _assign_and_submit(client, db_session, job, application, vp_evaluator, hr_headers, "interview_round_3", 3)

    profile = client.get(f"/hr/applications/{application.id}/profile", headers=hr_headers).json()
    # score=90 among [90, 60]: 1 below, 1 tied (itself) -> (1+0.5)/2*100.
    assert profile["exam_percentile"] == 75.0
    # 0.30*5 + 0.30*4 + 0.40*3 = 3.9
    assert profile["evaluator_consensus_score"] == 3.9
    assert profile["interview_rubric_score"] == MOCK_RUBRIC_SCORE

    expected_final_score = compute_final_synthesis_score(
        skill_score=80.0,
        exam_percentile=75.0,
        executive_consensus_score=3.9 * 20,
        interview_rubric_score=MOCK_RUBRIC_SCORE,
    )
    assert profile["final_synthesis_score"] == expected_final_score


def test_applicant_sees_own_exam_score_and_percentile_once_recorded(
    client, db_session, make_job, make_application, applicant, hr_admin, make_user
):
    """The applicant-facing counterpart to test_exam_percentile_and_
    final_synthesis_score above: same percentile math, but read from
    the applicant's own endpoint, where Skill Matching's score/gaps
    deliberately never appear -- this field is different, a plain fact,
    not a subjective AI critique."""
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    applicant_headers = auth_headers(client, applicant.email)

    other_applicant = make_user("other-exam-applicant@arkivetesting.com", UserRole.applicant)
    other_application = create_application_with_stage_instances(
        db_session, applicant_id=other_applicant.id, requisition=job
    )
    db_session.flush()

    _advance_to(client, application, "examination", hr_headers, FULL_WORKFLOW)
    _advance_to(client, other_application, "examination", hr_headers, FULL_WORKFLOW)

    # Before HR records anything, the applicant sees no result yet.
    detail = client.get(f"/applicant/applications/{application.id}", headers=applicant_headers).json()
    assert detail["examination_results"] == {}
    assert detail["exam_percentile"] is None

    resp = client.patch(
        f"/hr/applications/{application.id}/examination-result",
        json={"stage_type": "examination", "score": 90},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text
    resp = client.patch(
        f"/hr/applications/{other_application.id}/examination-result",
        json={"stage_type": "examination", "score": 60},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text

    detail = client.get(f"/applicant/applications/{application.id}", headers=applicant_headers).json()
    assert detail["examination_results"]["examination"]["score"] == 90
    # score=90 among [90, 60]: 1 below, 1 tied (itself) -> (1+0.5)/2*100.
    assert detail["exam_percentile"] == 75.0


def test_hr_booking_an_exam_session_notifies_applicant(client, db_session, make_job, make_application, applicant, hr_admin):
    """HR booking an applicant into an exam session fires an in-app
    Notification to them, alongside the email."""
    from app.models.exam_slot import ExamSlot

    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    applicant_headers = auth_headers(client, applicant.email)

    _advance_to(client, application, "examination", hr_headers, FULL_WORKFLOW)
    slot = ExamSlot(requisition_id=job.id, stage_type="examination", date="2030-09-01", time="10:00",
                    end_time="12:00", location="Room 204", capacity=10)
    db_session.add(slot)
    db_session.flush()

    resp = client.post(
        f"/hr/applications/{application.id}/exam-booking",
        json={"stage_type": "examination", "exam_slot_id": slot.id},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text

    notifications = client.get("/notifications", headers=applicant_headers).json()
    assert notifications["unread_count"] == 1
    assert "Sun, 1 Sep 2030" in notifications["items"][0]["message"]
    assert notifications["items"][0]["link"] == f"/applicant/applications/{application.id}"


def test_final_decision_board_ranks_candidates_descending(
    client, db_session, make_job, make_application, hr_admin, evaluator, make_user
):
    job = make_job(FULL_WORKFLOW)
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    dept_evaluator = make_user("dept3-test@arkivetesting.com", evaluator.role)
    vp_evaluator = make_user("vp3-test@arkivetesting.com", evaluator.role)

    # Strong candidate: VP=5 puts them first regardless of HR/Dept.
    strong_applicant = make_user("strong-applicant@arkivetesting.com", UserRole.applicant)
    strong_application = create_application_with_stage_instances(
        db_session, applicant_id=strong_applicant.id, requisition=job
    )
    db_session.flush()
    _advance_to(client, strong_application, "interview_round_3", hr_headers, FULL_WORKFLOW)
    _assign_and_submit(client, db_session, job, strong_application, evaluator, hr_headers, "interview_round_1", 4)
    _assign_and_submit(client, db_session, job, strong_application, dept_evaluator, hr_headers, "interview_round_2", 4)
    _assign_and_submit(client, db_session, job, strong_application, vp_evaluator, hr_headers, "interview_round_3", 5)

    # Weaker candidate: VP=2, should rank below the strong one.
    weak_applicant = make_user("weak-applicant@arkivetesting.com", UserRole.applicant)
    weak_application = create_application_with_stage_instances(
        db_session, applicant_id=weak_applicant.id, requisition=job
    )
    db_session.flush()
    weak_hr = make_user("weak-hr@arkivetesting.com", evaluator.role)
    weak_dept = make_user("weak-dept@arkivetesting.com", evaluator.role)
    weak_vp = make_user("weak-vp@arkivetesting.com", evaluator.role)
    _advance_to(client, weak_application, "interview_round_3", hr_headers, FULL_WORKFLOW)
    _assign_and_submit(client, db_session, job, weak_application, weak_hr, hr_headers, "interview_round_1", 4)
    _assign_and_submit(client, db_session, job, weak_application, weak_dept, hr_headers, "interview_round_2", 4)
    _assign_and_submit(client, db_session, job, weak_application, weak_vp, hr_headers, "interview_round_3", 2)

    resp = client.get(f"/hr/requisitions/{job.id}/final-decision-board", headers=hr_headers)
    assert resp.status_code == 200, resp.text
    board = resp.json()
    assert board["job_title"] == job.title
    assert [e["application_id"] for e in board["entries"]] == [strong_application.id, weak_application.id]
    assert board["entries"][0]["vp_score"] == 5.0
    assert board["entries"][1]["vp_score"] == 2.0


def test_final_synthesis_score_none_until_all_inputs_ready(
    client, db_session, make_job, make_application, hr_admin, evaluator
):
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    _advance_to(client, application, "interview_round_1", hr_headers, FULL_WORKFLOW)
    _assign_and_submit(client, db_session, job, application, evaluator, hr_headers, "interview_round_1", 4)

    profile = client.get(f"/hr/applications/{application.id}/profile", headers=hr_headers).json()
    # only one of the four WSM inputs exists so far -- no exam score, no
    # skill match score yet, so final_synthesis_score must stay None
    # rather than silently treating the missing inputs as zero
    assert profile["final_synthesis_score"] is None


# ---------------------------------------------------------------------------
# Exam-slot CRUD (backend/app/api/hr/) — no prior coverage.
# ---------------------------------------------------------------------------


def test_add_exam_slot_success(client, hr_admin, make_job):
    job = make_job(FULL_WORKFLOW)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        f"/hr/requisitions/{job.id}/exam-slots",
        json={"stage_type": "examination", "date": "2027-02-01", "time": "09:00", "location": "Room 101", "capacity": 10},
        headers=headers,
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["remaining_capacity"] == 10


def test_add_exam_slot_rejects_non_exam_stage(client, hr_admin, make_job):
    job = make_job(FULL_WORKFLOW)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        f"/hr/requisitions/{job.id}/exam-slots",
        json={"stage_type": "interview_round_1", "date": "2027-02-01", "time": "09:00", "location": "Room 101", "capacity": 10},
        headers=headers,
    )

    assert resp.status_code == 422


def test_list_exam_slots(client, hr_admin, make_job):
    job = make_job(FULL_WORKFLOW)
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    client.post(
        f"/hr/requisitions/{job.id}/exam-slots",
        json={"stage_type": "examination", "date": "2027-02-01", "time": "09:00", "location": "Room 101", "capacity": 5},
        headers=headers,
    )

    resp = client.get(f"/hr/requisitions/{job.id}/exam-slots", headers=headers)

    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 1
    assert resp.json()[0]["location"] == "Room 101"


def test_remove_exam_slot_success(client, hr_admin, make_job):
    job = make_job(FULL_WORKFLOW)
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    slot_id = client.post(
        f"/hr/requisitions/{job.id}/exam-slots",
        json={"stage_type": "examination", "date": "2027-02-01", "time": "09:00", "location": "Room 101", "capacity": 5},
        headers=headers,
    ).json()["id"]

    resp = client.delete(f"/hr/requisitions/{job.id}/exam-slots/{slot_id}", headers=headers)
    assert resp.status_code == 204, resp.text

    remaining = client.get(f"/hr/requisitions/{job.id}/exam-slots", headers=headers).json()
    assert remaining == []


def test_remove_exam_slot_blocked_while_approved_booking_exists(
    client, db_session, hr_admin, make_job, make_application
):
    from app.models.enums import ExamBookingStatus
    from app.models.exam_slot import ExamSlot
    from app.models.exam_slot_booking import ExamSlotBooking

    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    slot = ExamSlot(requisition_id=job.id, stage_type="examination", date="2027-02-01", time="09:00", location="Room 101", capacity=5)
    db_session.add(slot)
    db_session.flush()
    instance = (
        db_session.query(StageInstance)
        .filter(StageInstance.application_id == application.id, StageInstance.stage_type == StageType.examination)
        .one()
    )
    db_session.add(
        ExamSlotBooking(
            exam_slot_id=slot.id,
            application_id=application.id,
            stage_instance_id=instance.id,
            applicant_selected_slot_ids=[slot.id],
            status=ExamBookingStatus.approved,
        )
    )
    db_session.flush()

    resp = client.delete(f"/hr/requisitions/{job.id}/exam-slots/{slot.id}", headers=headers)
    assert resp.status_code == 409, resp.text


def test_resolve_exam_booking_approve_writes_schedule(client, db_session, hr_admin, make_job, make_application):
    from app.models.enums import ExamBookingStatus
    from app.models.exam_slot import ExamSlot
    from app.models.exam_slot_booking import ExamSlotBooking

    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    slot = ExamSlot(requisition_id=job.id, stage_type="examination", date="2027-02-01", time="09:00", location="Room 101", capacity=5)
    db_session.add(slot)
    db_session.flush()
    instance = (
        db_session.query(StageInstance)
        .filter(StageInstance.application_id == application.id, StageInstance.stage_type == StageType.examination)
        .one()
    )
    booking = ExamSlotBooking(
        exam_slot_id=slot.id,
        application_id=application.id,
        stage_instance_id=instance.id,
        applicant_selected_slot_ids=[slot.id],
    )
    db_session.add(booking)
    db_session.flush()

    resp = client.post(
        f"/hr/applications/{application.id}/exam-bookings/{booking.id}/resolve",
        json={"decision": "approve"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    exam = resp.json()["examinations"]["examination"]
    assert exam["schedule"] == {"date": "2027-02-01", "time": "09:00", "location": "Room 101"}
    assert exam["pending_booking"] is None

    # Already resolved — a second resolve on the same booking must be
    # rejected, not silently re-applied.
    resp = client.post(
        f"/hr/applications/{application.id}/exam-bookings/{booking.id}/resolve",
        json={"decision": "approve"},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text


def test_resolve_exam_booking_deny_leaves_unscheduled(client, db_session, hr_admin, make_job, make_application):
    from app.models.exam_slot import ExamSlot
    from app.models.exam_slot_booking import ExamSlotBooking

    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    slot = ExamSlot(requisition_id=job.id, stage_type="examination", date="2027-02-01", time="09:00", location="Room 101", capacity=5)
    db_session.add(slot)
    db_session.flush()
    instance = (
        db_session.query(StageInstance)
        .filter(StageInstance.application_id == application.id, StageInstance.stage_type == StageType.examination)
        .one()
    )
    booking = ExamSlotBooking(
        exam_slot_id=slot.id,
        application_id=application.id,
        stage_instance_id=instance.id,
        applicant_selected_slot_ids=[slot.id],
    )
    db_session.add(booking)
    db_session.flush()

    resp = client.post(
        f"/hr/applications/{application.id}/exam-bookings/{booking.id}/resolve",
        json={"decision": "deny"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    exam = resp.json()["examinations"]["examination"]
    assert exam["schedule"] is None
    assert exam["pending_booking"] is None


# ---------------------------------------------------------------------------
# Requisition-evaluator pool DELETE (backend/app/api/hr/) — no
# prior coverage; add/list were already covered in test_evaluator.py.
# ---------------------------------------------------------------------------


def test_remove_requisition_evaluator_success(client, hr_admin, evaluator, make_job):
    job = make_job(FULL_WORKFLOW)
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    client.post(f"/hr/requisitions/{job.id}/evaluators", json={"evaluator_id": evaluator.id}, headers=headers)

    resp = client.delete(f"/hr/requisitions/{job.id}/evaluators/{evaluator.id}", headers=headers)
    assert resp.status_code == 204, resp.text

    pool = client.get(f"/hr/requisitions/{job.id}/evaluators", headers=headers).json()
    assert pool == []


def test_remove_requisition_evaluator_blocked_while_assigned(
    client, db_session, hr_admin, evaluator, make_job, make_application
):
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    client.post(f"/hr/requisitions/{job.id}/evaluators", json={"evaluator_id": evaluator.id}, headers=headers)

    _advance_to(client, application, "interview_round_1", headers, FULL_WORKFLOW)
    resp = client.post(
        f"/hr/applications/{application.id}/interview-assignment",
        json={"stage_type": "interview_round_1", "evaluator_id": evaluator.id},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    resp = client.delete(f"/hr/requisitions/{job.id}/evaluators/{evaluator.id}", headers=headers)
    assert resp.status_code == 409, resp.text


# ---------------------------------------------------------------------------
# set_interview_schedule (backend/app/api/hr/) — no prior
# coverage; mirrors set_examination_schedule, already covered.
# ---------------------------------------------------------------------------


def test_set_interview_schedule_writes_schedule(client, db_session, hr_admin, evaluator, make_job, make_application):
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    _advance_to(client, application, "interview_round_1", headers, FULL_WORKFLOW)

    resp = client.post(
        f"/hr/applications/{application.id}/interview-schedule",
        json={"stage_type": "interview_round_1", "date": "2027-03-01", "time": "13:00", "mode": "online", "meeting_link": "https://meet.example.com/x"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    schedule = resp.json()["interview_ratings"]["interview_round_1"]["schedule"]
    assert schedule["date"] == "2027-03-01"
    assert schedule["meeting_link"] == "https://meet.example.com/x"


# ---------------------------------------------------------------------------
# regression: the executive triplet is read from the job's own workflow
# ordering, not a hardcoded interview_round_1/2/3 name triple.
#
# before this, _consolidate_executive_scores and get_final_decision_board
# both looked up those three literal names. every job created by the demo
# seed uses the *legacy* names (interview_hr_director/dept_head/vp), so
# Algorithm 04's 30/30/40 weighting never fired and the Final Decision
# Board returned zero entries for every requisition in the database.
# ---------------------------------------------------------------------------

LEGACY_EXEC_WORKFLOW = [
    "document_upload",
    "skill_matching",
    "examination",
    "interview_hr_director",
    "interview_dept_head",
    "interview_vp",
    "final_decision",
]

FOUR_ROUND_WORKFLOW = [
    "document_upload",
    "interview_round_1",
    "interview_round_2",
    "interview_round_3",
    "interview_round_4",
    "final_decision",
]


def test_legacy_named_workflow_gets_algorithm_04_weighting(
    client, db_session, make_job, make_application, hr_admin, evaluator, make_user
):
    """5/3/1 weights to 2.8 under 30/30/40 but averages to 3.0 — so this
    asserts the *weighted* formula fired on a legacy-named workflow, not
    a silent equal-weighted fallback."""
    job = make_job(LEGACY_EXEC_WORKFLOW, title="Legacy Exec Chain")
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    dept_evaluator = make_user("legacy-dept@arkivetesting.com", evaluator.role)
    vp_evaluator = make_user("legacy-vp@arkivetesting.com", evaluator.role)

    _advance_to(client, application, "interview_vp", hr_headers, LEGACY_EXEC_WORKFLOW)
    _assign_and_submit(client, db_session, job, application, evaluator, hr_headers, "interview_hr_director", 5)
    _assign_and_submit(client, db_session, job, application, dept_evaluator, hr_headers, "interview_dept_head", 3)
    _assign_and_submit(client, db_session, job, application, vp_evaluator, hr_headers, "interview_vp", 1)

    profile = client.get(f"/hr/applications/{application.id}/profile", headers=hr_headers).json()
    assert profile["evaluator_consensus_score"] == 2.8
    assert profile["evaluator_consensus_score"] != 3.0


def test_legacy_named_workflow_appears_on_final_decision_board(
    client, db_session, make_job, make_application, hr_admin, evaluator, make_user
):
    """Guards against an empty board for these jobs: filtering on the
    interview_round_1/2/3 keys would miss them, since a legacy workflow
    never has those."""
    job = make_job(LEGACY_EXEC_WORKFLOW, title="Legacy Board Job")
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    dept_evaluator = make_user("board-dept@arkivetesting.com", evaluator.role)
    vp_evaluator = make_user("board-vp@arkivetesting.com", evaluator.role)

    _advance_to(client, application, "interview_vp", hr_headers, LEGACY_EXEC_WORKFLOW)
    _assign_and_submit(client, db_session, job, application, evaluator, hr_headers, "interview_hr_director", 4)
    _assign_and_submit(client, db_session, job, application, dept_evaluator, hr_headers, "interview_dept_head", 3)
    _assign_and_submit(client, db_session, job, application, vp_evaluator, hr_headers, "interview_vp", 5)

    resp = client.get(f"/hr/requisitions/{job.id}/final-decision-board", headers=hr_headers)
    assert resp.status_code == 200, resp.text
    entries = resp.json()["entries"]
    assert [e["application_id"] for e in entries] == [application.id]
    # Positional, in workflow order: hr_director -> dept_head -> vp.
    assert (entries[0]["hr_score"], entries[0]["dept_score"], entries[0]["vp_score"]) == (4.0, 3.0, 5.0)


def test_four_round_workflow_still_falls_back_to_equal_weighted_mean(
    client, db_session, make_job, make_application, hr_admin, evaluator, make_user
):
    """Guards the other side of the change: keying on *count* must not
    over-apply Algorithm 04 to a workflow that isn't the 3-role executive
    chain. 5/3/1/3 averages to 3.0; no 30/30/40 reading of four rounds
    exists, so the mean is the only correct answer."""
    job = make_job(FOUR_ROUND_WORKFLOW, title="Four Round Job")
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    e2 = make_user("four-r2@arkivetesting.com", evaluator.role)
    e3 = make_user("four-r3@arkivetesting.com", evaluator.role)
    e4 = make_user("four-r4@arkivetesting.com", evaluator.role)

    _advance_to(client, application, "interview_round_4", hr_headers, FOUR_ROUND_WORKFLOW)
    _assign_and_submit(client, db_session, job, application, evaluator, hr_headers, "interview_round_1", 5)
    _assign_and_submit(client, db_session, job, application, e2, hr_headers, "interview_round_2", 3)
    _assign_and_submit(client, db_session, job, application, e3, hr_headers, "interview_round_3", 1)
    _assign_and_submit(client, db_session, job, application, e4, hr_headers, "interview_round_4", 3)

    profile = client.get(f"/hr/applications/{application.id}/profile", headers=hr_headers).json()
    assert profile["evaluator_consensus_score"] == 3.0

    # And a 4-round job must not appear on the executive board at all.
    resp = client.get(f"/hr/requisitions/{job.id}/final-decision-board", headers=hr_headers)
    assert resp.json()["entries"] == []
