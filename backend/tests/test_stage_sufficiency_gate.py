"""The sufficiency gate on POST /applications/{id}/transition.

Sibling to test_transitions.py, which covers the DFA -- that one asks
whether a move is *legal*; this one asks whether the stage being left
actually produced anything.

Why it exists: application 2 in the dev database reached a hire with its
HR Administrator interview marked `complete` and no scorecard behind it.
The DFA had nothing to say, since every transition was adjacent and in
order -- a finite automaton reads current/requested state and by
construction can't look inside a payload, so catching an empty stage was
never its job. Nothing else was doing it either; the hire gate at the
very end of the pipeline was the first place anything noticed.
"""

from sqlalchemy import select

from app.models.enums import StageStatus, StageType
from app.models.stage_instance import StageInstance
from tests.conftest import auth_headers

WORKFLOW = [
    "document_upload",
    "skill_matching",
    "examination",
    "interview_round_1",
    "final_decision",
    "onboarding",
]

ACK = "Candidate withdrew before the panel could sit."


def _hr(client):
    return auth_headers(client, "hr-test@arkivetesting.com")


def _advance(client, application, target, headers, **extra):
    return client.post(
        f"/applications/{application.id}/transition",
        json={"target_stage": target, **extra},
        headers=headers,
    )


def _to(client, application, target, headers):
    """Walk to `target`, acknowledging whatever is hollow on the way."""
    workflow = WORKFLOW
    start = workflow.index(application.current_stage.value) + 1
    for stage in workflow[start : workflow.index(target) + 1]:
        resp = _advance(
            client, application, stage, headers,
            acknowledged_incomplete=True, reason="Test setup.",
        )
        assert resp.status_code == 200, resp.text


def _stage(db_session, application, stage_type):
    """Read the StageInstance row directly. CandidateProfile deliberately
    exposes no stage list, and the status/payload this gate writes is
    exactly what has to be asserted on."""
    db_session.expire_all()
    return db_session.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType(stage_type),
        )
    )


# --- The refusal ------------------------------------------------------


def test_an_interview_with_no_scorecard_refuses_the_advance(
    client, make_job, make_application, hr_admin
):
    job = make_job(WORKFLOW)
    application = make_application(job)
    headers = _hr(client)
    _to(client, application, "interview_round_1", headers)

    resp = _advance(client, application, "final_decision", headers)

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "stage_incomplete"
    assert [b["key"] for b in detail["blockers"]] == ["scorecard"]


def test_the_refusal_names_the_stage_in_hr_s_own_words(
    client, make_job, make_application, hr_admin
):
    """The blocker list is structured, but the message a human reads has
    to say which round — 'interview_round_1' is not a stage name anyone
    at MSEUF uses."""
    job = make_job(WORKFLOW)
    application = make_application(job)
    headers = _hr(client)
    _to(client, application, "interview_round_1", headers)

    detail = _advance(client, application, "final_decision", headers).json()["detail"]
    assert "interview_round_1" not in detail["message"]


def test_a_refused_advance_changes_nothing(client, db_session, make_job, make_application, hr_admin):
    """Same guarantee the DFA refusal already makes: a rejected
    transition leaves every row exactly as it was."""
    job = make_job(WORKFLOW)
    application = make_application(job)
    headers = _hr(client)
    _to(client, application, "interview_round_1", headers)

    _advance(client, application, "final_decision", headers)

    profile = client.get(f"/hr/applications/{application.id}/profile", headers=headers).json()
    assert profile["current_stage"] == "interview_round_1"
    assert _stage(db_session, application, "interview_round_1").status.value == "in_progress"


def test_an_exam_with_a_schedule_but_no_score_is_refused(
    client, db_session, make_job, make_application, hr_admin
):
    """Booking an exam is not sitting one. This is the shape that got
    through on the real records: a schedule, and nothing else."""
    from app.models.exam_slot import ExamSlot

    job = make_job(WORKFLOW)
    application = make_application(job)
    headers = _hr(client)
    _to(client, application, "examination", headers)
    slot = ExamSlot(requisition_id=job.id, stage_type="examination", date="2030-09-10", time="09:00",
                    end_time="11:00", location="Room 101", capacity=10)
    db_session.add(slot)
    db_session.flush()

    resp = client.post(
        f"/hr/applications/{application.id}/exam-booking",
        json={"stage_type": "examination", "exam_slot_id": slot.id},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    resp = _advance(client, application, "interview_round_1", headers)
    assert resp.status_code == 409, resp.text
    assert [b["key"] for b in resp.json()["detail"]["blockers"]] == ["exam_score"]


# --- The override -----------------------------------------------------


def test_acknowledging_lets_it_through_and_records_it_as_skipped(
    client, db_session, make_job, make_application, hr_admin
):
    """The gate is a speed bump, not a wall — HR keeps the final call.
    What changes is that the record stops claiming the stage happened."""
    job = make_job(WORKFLOW)
    application = make_application(job)
    headers = _hr(client)
    _to(client, application, "interview_round_1", headers)

    resp = _advance(
        client, application, "final_decision", headers,
        acknowledged_incomplete=True, reason=ACK,
    )
    assert resp.status_code == 200, resp.text

    stage = _stage(db_session, application, "interview_round_1")
    assert stage.status.value == "skipped"


def test_the_override_records_who_said_so_and_why(
    client, db_session, make_job, make_application, hr_admin
):
    """An override with no reason attached is the anomaly that produced
    application 100 — a decision with a name on it and no account of
    itself."""
    job = make_job(WORKFLOW)
    application = make_application(job)
    headers = _hr(client)
    _to(client, application, "interview_round_1", headers)

    _advance(client, application, "final_decision", headers,
             acknowledged_incomplete=True, reason=ACK)

    skipped = _stage(db_session, application, "interview_round_1").payload["skipped"]
    assert skipped["reason"] == ACK
    assert skipped["missing"] == ["scorecard"]
    assert skipped["acknowledged_by"] == str(hr_admin.id)
    assert skipped["acknowledged_at"]


def test_a_stage_with_its_evidence_is_complete_not_skipped(
    client, db_session, make_job, make_application, hr_admin
):
    """The gate must not mark everything skipped — a stage that did its
    job still reads as complete."""
    job = make_job(WORKFLOW)
    application = make_application(job)
    headers = _hr(client)
    _to(client, application, "examination", headers)

    client.patch(
        f"/hr/applications/{application.id}/examination-result",
        json={"stage_type": "examination", "score": 88.0},
        headers=headers,
    )
    assert _advance(client, application, "interview_round_1", headers).status_code == 200

    stage = _stage(db_session, application, "examination")
    assert stage.status.value == "complete"
    assert "skipped" not in (stage.payload or {})


# --- Precedence and scope --------------------------------------------


def test_an_illegal_move_is_still_refused_by_the_dfa_first(
    client, make_job, make_application, hr_admin
):
    """Order matters. Telling someone their scorecard is missing on a
    move that was never legal in the first place is noise — the DFA
    answers first, and acknowledging incompleteness does not buy a jump."""
    job = make_job(WORKFLOW)
    application = make_application(job)
    headers = _hr(client)
    _to(client, application, "examination", headers)

    resp = _advance(client, application, "onboarding", headers,
                    acknowledged_incomplete=True, reason="Trying to skip ahead.")
    assert resp.status_code == 422, resp.text


def test_document_upload_will_not_advance_without_a_resume(
    client, make_job, make_application, hr_admin
):
    """`resume` became transition-blocking on 2026-09-06. It had been
    excluded on the reasoning that the gate "would only ever fire on the
    HR route, blocking a walk-in or paper application" — and no such
    application can exist: POST /applications is the only route that
    creates one and it is gated to the applicant role. Meanwhile the real
    case was open — HR could advance a candidate past Document Upload
    with no resume at all, which is the "advanced without uploading
    anything" case round-2 testing reported."""
    job = make_job(WORKFLOW)
    application = make_application(job)
    headers = _hr(client)

    resp = _advance(client, application, "skill_matching", headers)

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "stage_incomplete"
    assert [b["key"] for b in detail["blockers"]] == ["resume"]


def test_hr_can_still_advance_without_a_resume_by_acknowledging_it(
    client, db_session, make_job, make_application, hr_admin
):
    """A speed bump, not a wall — the same shape every other gate here
    has. The stage lands as `skipped`, never `complete`, carrying the
    reason and the acknowledging actor."""
    job = make_job(WORKFLOW)
    application = make_application(job)
    headers = _hr(client)

    resp = client.post(
        f"/applications/{application.id}/transition",
        json={
            "target_stage": "skill_matching",
            "acknowledged_incomplete": True,
            "reason": "Paper application received at the HR desk.",
        },
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    instance = db_session.query(StageInstance).filter(
        StageInstance.application_id == application.id,
        StageInstance.stage_type == StageType.document_upload,
    ).one()
    assert instance.status == StageStatus.skipped
    assert instance.payload["skipped"]["missing"] == ["resume"]
    assert instance.payload["skipped"]["reason"] == "Paper application received at the HR desk."


def test_the_ai_match_score_reports_but_does_not_block(
    client, make_job, make_application, make_resume, hr_admin
):
    """skill_matching's score is produced by an agent, not by a person.
    Refusing the transition would punish HR for something they cannot
    fix from that screen, so it is reported and left to judgement."""
    job = make_job(WORKFLOW)
    application = make_application(job)
    # A resume, because Document Upload will not advance without one —
    # a different rule from the one under test here.
    make_resume(application)
    headers = _hr(client)

    assert _advance(client, application, "skill_matching", headers).status_code == 200
    assert _advance(client, application, "examination", headers).status_code == 200
