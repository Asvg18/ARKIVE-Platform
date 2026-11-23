"""Tests for the hire/reject decision gate -- services/hire_decision.py
and the guard rail + paper trail on PATCH /hr/applications/{id}/status.

Motivating defect: that endpoint was a bare `application.status =
body.status; db.commit()`. Application 100 in the dev database was
`hired` while still sitting at its *first* interview round with zero
scorecards, and nothing recorded that as unusual -- the hollow record
that made the Decision Support synthesis render blank in the first
place.

What these tests are most careful about is that the gate stays a speed
bump, not a wall. ApplicationStatus is decoupled from the DFA
deliberately, so "HR can always still hire" is a requirement here, not a
loophole."""

from app.models.enums import StageType, UserRole
from app.models.stage_instance import StageInstance
from app.services.applications import create_application_with_stage_instances
from tests.conftest import auth_headers
from tests.test_decision_support import FULL_WORKFLOW, _advance_to, _assign_and_submit
from tests.test_synthesis import NO_SCREENING_WORKFLOW, _set_match_score

# no final_decision stage at all -- every workflow the Job Opening
# Builder offers has one, but a legacy or hand-authored job might not,
# and an application on such a job must still be able to record its
# outcome
NO_FINAL_DECISION_WORKFLOW = ["document_upload", "interview_round_1", "onboarding"]


def _blockers(resp) -> list[dict]:
    return resp.json()["detail"]["blockers"]


def _decisions(db_session, application) -> list[dict]:
    """The raw append-only decision log off the final_decision stage
    payload — what the API's read model is built from."""
    instance = (
        db_session.query(StageInstance)
        .filter(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.final_decision,
        )
        .one_or_none()
    )
    if instance is None:
        return []
    return (instance.payload or {}).get("decisions", [])


def _complete_the_record(client, db_session, job, application, headers, evaluator, make_user):
    """Walks a FULL_WORKFLOW application all the way to a record with
    nothing outstanding: all four WSM criteria available and the
    candidate standing at final_decision."""
    other_applicant = make_user("hire-other@arkivetesting.com", UserRole.applicant)
    other_application = create_application_with_stage_instances(
        db_session, applicant_id=other_applicant.id, requisition=job
    )
    db_session.flush()

    _advance_to(client, application, "examination", headers, FULL_WORKFLOW)
    _advance_to(client, other_application, "examination", headers, FULL_WORKFLOW)
    for target, score in ((application, 88), (other_application, 55)):
        resp = client.patch(
            f"/hr/applications/{target.id}/examination-result",
            json={"stage_type": "examination", "score": score},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

    _set_match_score(db_session, application, 80.0)

    dept = make_user("hire-dept@arkivetesting.com", evaluator.role)
    vp = make_user("hire-vp@arkivetesting.com", evaluator.role)
    _advance_to(client, application, "final_decision", headers, FULL_WORKFLOW)
    _assign_and_submit(client, db_session, job, application, evaluator, headers, "interview_round_1", 5)
    _assign_and_submit(client, db_session, job, application, dept, headers, "interview_round_2", 4)
    _assign_and_submit(client, db_session, job, application, vp, headers, "interview_round_3", 3)


def test_hiring_an_empty_record_is_refused_and_says_why(
    client, db_session, make_job, make_application, hr_admin
):
    """The application-100 scenario: a candidate at the very start of the
    pipeline with nothing recorded. Previously a 200."""
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch(
        f"/hr/applications/{application.id}/status",
        json={"status": "hired"},
        headers=hr_headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "incomplete_record"

    blockers = _blockers(resp)
    keys = {b["key"] for b in blockers}
    assert "stage" in keys
    assert "interview_round" in keys

    # The stage blocker is the sharpest signal a panel would ask about —
    # it names where the candidate actually stood.
    stage_blocker = next(b for b in blockers if b["key"] == "stage")
    assert "Document Upload" in stage_blocker["label"]

    # Nothing was written: refusing must not half-apply the decision.
    assert db_session.get(type(application), application.id).status.value == "active"
    assert _decisions(db_session, application) == []


def test_outstanding_rounds_are_named_individually_not_rolled_into_one_criterion(
    client, db_session, make_job, make_application, hr_admin
):
    """The two interview-derived WSM criteria are suppressed while the
    rounds themselves are already listed — otherwise HR reads the same
    fact three times ("Round 2 missing", "Round 3 missing", "Executive
    Consensus missing") and the list stops being scannable."""
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch(
        f"/hr/applications/{application.id}/status",
        json={"status": "hired"},
        headers=hr_headers,
    )
    assert resp.status_code == 409, resp.text
    blockers = _blockers(resp)

    criterion_labels = {b["label"] for b in blockers if b["key"] == "criterion"}
    assert "Executive Consensus" not in criterion_labels
    assert "Interview Rubric Coverage" not in criterion_labels
    # The criteria that are genuinely their own separate fact still show.
    assert "Skill Match" in criterion_labels

    round_labels = {b["label"] for b in blockers if b["key"] == "interview_round"}
    assert len(round_labels) == 3


def test_acknowledging_an_incomplete_record_lets_the_hire_through_and_records_it(
    client, db_session, make_job, make_application, hr_admin
):
    """The escape hatch. HR must always be able to hire — what changes is
    that the incompleteness is now stated and stored."""
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch(
        f"/hr/applications/{application.id}/status",
        json={
            "status": "hired",
            "acknowledged_incomplete": True,
            "reason": "Internal transfer — panel already interviewed her last quarter.",
        },
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "hired"

    profile = client.get(
        f"/hr/applications/{application.id}/profile", headers=hr_headers
    ).json()
    decision = profile["decision"]
    assert decision["status"] == "hired"
    assert decision["previous_status"] == "active"
    assert decision["acknowledged_incomplete"] is True
    assert decision["reason"].startswith("Internal transfer")
    assert decision["decided_by_name"] == hr_admin.full_name
    # The field that makes a premature hire visible after the fact.
    assert decision["decided_at_stage_label"] == "Document Upload"
    # The blockers HR was shown are stored verbatim, so a reader of the
    # old record sees exactly what the decider saw.
    assert len(decision["blockers"]) == len(_blockers_for(client, application, hr_headers))


def _blockers_for(client, application, headers) -> list[dict]:
    """Re-derives the blocker list by asking for a fresh hire on a
    now-closed application — used only to assert the stored list matches
    what the gate reports."""
    resp = client.patch(
        f"/hr/applications/{application.id}/status",
        json={"status": "active"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    resp = client.patch(
        f"/hr/applications/{application.id}/status",
        json={"status": "hired"},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text
    return resp.json()["detail"]["blockers"]


def test_overriding_the_gate_without_a_reason_is_refused(
    client, db_session, make_job, make_application, hr_admin
):
    """The acknowledgement alone would leave the record no better off
    than before the gate existed — an unexplained hire with a name
    attached. A reason stays optional everywhere the gate does not
    apply."""
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch(
        f"/hr/applications/{application.id}/status",
        json={"status": "hired", "acknowledged_incomplete": True, "reason": "   "},
        headers=hr_headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "reason_required"
    assert _decisions(db_session, application) == []

    # Same request with an actual reason goes through.
    resp = client.patch(
        f"/hr/applications/{application.id}/status",
        json={
            "status": "hired",
            "acknowledged_incomplete": True,
            "reason": "Board approved the appointment out of cycle.",
        },
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text


def test_a_complete_record_hires_with_no_acknowledgement_needed(
    client, db_session, make_job, make_application, hr_admin, evaluator, make_user
):
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    _complete_the_record(client, db_session, job, application, hr_headers, evaluator, make_user)

    resp = client.patch(
        f"/hr/applications/{application.id}/status",
        json={"status": "hired", "reason": "Strongest candidate across all three rounds."},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text

    decision = client.get(
        f"/hr/applications/{application.id}/profile", headers=hr_headers
    ).json()["decision"]
    assert decision["acknowledged_incomplete"] is False
    assert decision["blockers"] == []
    # The snapshot is the point of the record: the score as it stood at
    # the moment of decision, frozen rather than recomputed later.
    assert decision["final_synthesis_score"] is not None
    assert decision["overall_tier"] is not None


def test_criteria_this_workflow_can_never_produce_do_not_block_the_hire(
    client, db_session, make_job, make_application, hr_admin, evaluator, make_user
):
    """The "streamlined" preset has no skill_matching and no examination
    stage, so two of the four WSM criteria are permanently unreachable
    and the final synthesis score can never exist. Blocking on those
    would make every job on that preset unhireable — a job-design problem
    to raise with HR, not a reason to refuse a decision."""
    job = make_job(NO_SCREENING_WORKFLOW, title="No-Screening Job")
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    dept = make_user("noscreen-dept@arkivetesting.com", evaluator.role)
    _advance_to(client, application, "final_decision", hr_headers, NO_SCREENING_WORKFLOW)
    _assign_and_submit(client, db_session, job, application, evaluator, hr_headers, "interview_round_1", 4)
    _assign_and_submit(client, db_session, job, application, dept, hr_headers, "interview_round_2", 4)

    resp = client.patch(
        f"/hr/applications/{application.id}/status",
        json={"status": "hired"},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text

    decision = client.get(
        f"/hr/applications/{application.id}/profile", headers=hr_headers
    ).json()["decision"]
    assert decision["acknowledged_incomplete"] is False
    # Unreachable criteria mean there is still no final score — and that
    # is fine. The record says so honestly rather than pretending.
    assert decision["final_synthesis_score"] is None


def test_rejecting_is_never_gated_but_is_still_recorded(
    client, db_session, make_job, make_application, hr_admin
):
    """Rejecting a candidate early is ordinary HR practice at any stage.
    Only hiring on an empty record is the anomaly — but both leave a
    trail."""
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch(
        f"/hr/applications/{application.id}/status",
        json={"status": "rejected", "reason": "Withdrew — accepted another offer."},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text

    decision = client.get(
        f"/hr/applications/{application.id}/profile", headers=hr_headers
    ).json()["decision"]
    assert decision["status"] == "rejected"
    assert decision["reason"] == "Withdrew — accepted another offer."
    # Recorded as incomplete without ever having been asked to
    # acknowledge it — the trail is honest about the state of the record
    # even where the gate does not apply.
    assert decision["acknowledged_incomplete"] is False
    assert decision["blockers"] != []


def test_reopening_appends_rather_than_overwriting_the_earlier_decision(
    client, db_session, make_job, make_application, hr_admin
):
    """Silent erasure is the same class of problem this endpoint exists
    to fix, so re-deciding must not destroy the first record."""
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    for body in (
        {"status": "rejected", "reason": "Not a fit for this role."},
        {"status": "active", "reason": "Reopening — the department reconsidered."},
        {"status": "hired", "acknowledged_incomplete": True, "reason": "Offered the junior post instead."},
    ):
        resp = client.patch(
            f"/hr/applications/{application.id}/status", json=body, headers=hr_headers
        )
        assert resp.status_code == 200, resp.text

    stored = _decisions(db_session, application)
    assert [d["status"] for d in stored] == ["rejected", "active", "hired"]
    assert [d["previous_status"] for d in stored] == ["active", "rejected", "active"]

    # The read model reports the latest, so the profile shows the
    # decision in force without losing the ones before it.
    decision = client.get(
        f"/hr/applications/{application.id}/profile", headers=hr_headers
    ).json()["decision"]
    assert decision["status"] == "hired"
    assert decision["reason"] == "Offered the junior post instead."


def test_a_repeated_status_update_records_nothing_new(
    client, db_session, make_job, make_application, hr_admin
):
    """A double-clicked button must not produce two identical entries in
    a permanent record."""
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    for _ in range(2):
        resp = client.patch(
            f"/hr/applications/{application.id}/status",
            json={"status": "rejected"},
            headers=hr_headers,
        )
        assert resp.status_code == 200, resp.text

    assert len(_decisions(db_session, application)) == 1


def test_a_workflow_with_no_final_decision_stage_still_records_the_outcome(
    client, db_session, make_job, make_application, hr_admin
):
    """Get-or-create rather than a plain lookup — an outcome must never
    be dropped just because the job was authored without the stage the
    record lives on."""
    job = make_job(NO_FINAL_DECISION_WORKFLOW, title="No Final Decision Job")
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch(
        f"/hr/applications/{application.id}/status",
        json={"status": "rejected", "reason": "Position withdrawn."},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text

    stored = _decisions(db_session, application)
    assert len(stored) == 1
    assert stored[0]["reason"] == "Position withdrawn."


def test_the_pre_201_package_carries_the_decision_and_its_exact_timestamp(
    client, db_session, make_job, make_application, hr_admin, evaluator, make_user
):
    """A 201 file records what the institution decided, not only what the
    candidate did. `hired_at` also stops being the approximated
    "last time this row changed" once a real decision timestamp exists."""
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    _complete_the_record(client, db_session, job, application, hr_headers, evaluator, make_user)
    resp = client.patch(
        f"/hr/applications/{application.id}/status",
        json={"status": "hired", "reason": "Unanimous across the chain."},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text

    package = client.get(
        f"/hr/applications/{application.id}/pre-201-package", headers=hr_headers
    ).json()
    assert package["decision"]["reason"] == "Unanimous across the chain."
    assert package["decision"]["decided_by_name"] == hr_admin.full_name
    assert package["hired_at"].startswith(package["decision"]["decided_at"][:19])


def test_an_application_closed_before_decisions_were_recorded_reads_as_none(
    client, db_session, make_job, make_application, hr_admin
):
    """Every final_decision row in the database today predates this
    feature, so "no record" is the normal case for existing data and must
    read as None rather than 500."""
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    profile = client.get(
        f"/hr/applications/{application.id}/profile", headers=hr_headers
    ).json()
    assert profile["decision"] is None


def _sent_emails(monkeypatch) -> list[dict]:
    """Captures what the decision endpoint hands to send_email_safely.

    Patched where it is *used*, not where it is defined -- applications/decisions.py
    imported the name at module load, so patching app.services.email would
    leave the router still holding the original function.
    """
    sent: list[dict] = []
    monkeypatch.setattr(
        "app.api.hr.applications.decisions.send_email_safely",
        lambda **kwargs: sent.append(kwargs) or True,
    )
    return sent


def test_hiring_emails_the_candidate(
    client, db_session, make_job, make_application, hr_admin, applicant, monkeypatch
):
    """The final decision is the message a candidate is actually waiting
    on, and the one they are least likely to be in the app to catch. It
    was in-app only until now."""
    sent = _sent_emails(monkeypatch)
    job = make_job(FULL_WORKFLOW, title="Emailed Role")
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch(
        f"/hr/applications/{application.id}/status",
        json={"status": "hired", "acknowledged_incomplete": True, "reason": "Strong fit."},
        headers=hr_headers,
    )

    assert resp.status_code == 200, resp.text
    assert len(sent) == 1
    assert sent[0]["to"] == applicant.email
    assert "Emailed Role" in sent[0]["subject"]
    assert applicant.full_name in sent[0]["body"]
    # points at the offer rather than inventing terms this system has no
    # knowledge of
    assert "offer" in sent[0]["body"].lower()


def test_rejecting_emails_the_candidate(
    client, db_session, make_job, make_application, hr_admin, applicant, monkeypatch
):
    sent = _sent_emails(monkeypatch)
    job = make_job(FULL_WORKFLOW, title="Declined Role")
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch(
        f"/hr/applications/{application.id}/status",
        json={"status": "rejected", "reason": "Stronger field."},
        headers=hr_headers,
    )

    assert resp.status_code == 200, resp.text
    assert len(sent) == 1
    assert sent[0]["to"] == applicant.email
    assert "Declined Role" in sent[0]["subject"]
    # HR's internal reason is theirs, not something to forward to the
    # candidate as the explanation for the decision
    assert "Stronger field." not in sent[0]["body"]


def test_withdrawing_does_not_email_the_candidate(
    client, db_session, make_job, make_application, hr_admin, monkeypatch
):
    """They withdrew. Mailing someone about their own action reads as a
    system that is not listening."""
    sent = _sent_emails(monkeypatch)
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch(
        f"/hr/applications/{application.id}/status",
        json={"status": "withdrawn"},
        headers=hr_headers,
    )

    assert resp.status_code == 200, resp.text
    assert sent == []


def test_a_failing_mail_server_cannot_break_a_recorded_decision(
    client, db_session, make_job, make_application, hr_admin, monkeypatch
):
    """send_email_safely swallows everything by contract. Pinned here
    because the failure it guards against -- HR records a hire, SMTP is
    down, the whole request 500s and the decision is lost -- is exactly
    the kind of coupling that looks harmless until the day it isn't."""
    def _explode(**kwargs):
        raise RuntimeError("mail server on fire")

    # Configured (with nowhere real to go), or send_email would stop at
    # "not configured" -- the conftest default -- and never reach SMTP.
    monkeypatch.setattr("app.infra.config.settings.smtp_host", "smtp.invalid")
    monkeypatch.setattr("app.infra.config.settings.smtp_username", "test")
    monkeypatch.setattr("app.infra.config.settings.smtp_password", "test")
    monkeypatch.setattr("app.services.email.smtplib.SMTP", _explode)
    job = make_job(FULL_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch(
        f"/hr/applications/{application.id}/status",
        json={"status": "rejected", "reason": "Not this time."},
        headers=hr_headers,
    )

    assert resp.status_code == 200, resp.text
    db_session.refresh(application)
    assert application.status.value == "rejected"


# Approve Hire at Final Decision also moves the candidate onto Onboarding
# (panel revision list, 15 Oct 2026: the separate "Advance to Onboarding"
# button was removed, and the applicant's checklist only accepts a
# submission while the application is on onboarding).
ONBOARDING_WORKFLOW = ["document_upload", "final_decision", "onboarding"]


def _hire_incomplete(client, application, headers):
    return client.patch(
        f"/hr/applications/{application.id}/status",
        json={"status": "hired", "acknowledged_incomplete": True, "reason": "Test: hire under review."},
        headers=headers,
    )


def test_hiring_at_final_decision_moves_the_candidate_to_onboarding(
    client, db_session, make_job, make_application, hr_admin
):
    job = make_job(ONBOARDING_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    _advance_to(client, application, "final_decision", hr_headers, ONBOARDING_WORKFLOW)

    resp = _hire_incomplete(client, application, hr_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "hired"

    db_session.refresh(application)
    assert application.current_stage == StageType.onboarding
    # the decision is still recorded on final_decision, which is now done
    assert _decisions(db_session, application)[-1]["status"] == "hired"


def test_hiring_before_final_decision_leaves_the_stage_alone(
    client, db_session, make_job, make_application, hr_admin
):
    job = make_job(ONBOARDING_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = _hire_incomplete(client, application, hr_headers)
    assert resp.status_code == 200, resp.text

    db_session.refresh(application)
    assert application.current_stage == StageType.document_upload


def test_the_next_step_at_final_decision_is_the_decision(
    client, db_session, make_job, make_application, hr_admin
):
    job = make_job(ONBOARDING_WORKFLOW)
    application = make_application(job)
    db_session.flush()
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    _advance_to(client, application, "final_decision", hr_headers, ONBOARDING_WORKFLOW)

    profile = client.get(f"/hr/applications/{application.id}/profile", headers=hr_headers).json()

    assert profile["next_steps"] == "Make the final hire or reject decision."
