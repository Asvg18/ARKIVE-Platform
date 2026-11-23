"""Bulk shortlisting by rank, the two letters that go with it, and the
confirmation a shortlisted candidate owes before examination.

The decision being modelled is one judgement about a job -- HR reads a
ranked field and draws a line across it -- not N judgements about N
people. What these tests are most careful about is the two ways that can
quietly go wrong: someone being told they missed a cut they were never
actually ranked in, and someone being booked into an examination they
never agreed to sit.
"""

from sqlalchemy import select

from app.models.enums import ApplicationStatus, StageStatus, StageType
from app.models.notification import Notification
from app.models.stage_instance import StageInstance
from app.services import shortlisting
from tests.conftest import auth_headers

WORKFLOW = [
    "document_upload",
    "skill_matching",
    "shortlisting",
    "examination",
    "final_decision",
]

LETTERS = {
    "stage_type": "shortlisting",
    "shortlisted_letter": "You impressed the panel and we would like you to sit the exam.",
    "not_shortlisted_letter": "You were not picked this time. Please do watch for other openings.",
}


def pick(*applications):
    """The request body for shortlisting exactly these candidates."""
    return {**LETTERS, "shortlisted_application_ids": [a.id for a in applications]}


def _park_on_shortlisting(db_session, application, *, match_score=None):
    """Puts an application where a shortlisting decision is actually
    owed, with the score the ranking reads."""
    application.current_stage = StageType.shortlisting
    for instance in db_session.query(StageInstance).filter(
        StageInstance.application_id == application.id
    ):
        if instance.stage_type == StageType.skill_matching and match_score is not None:
            instance.payload = {"match_score": match_score}
            instance.status = StageStatus.complete
        if instance.stage_type == StageType.shortlisting:
            instance.status = StageStatus.in_progress
    db_session.flush()


def _sent(monkeypatch):
    sent: list[dict] = []
    # patched where it is used: the per-candidate and the bulk shortlist
    # live in two modules of the applications package
    for module in ("app.api.hr.applications.outcomes", "app.api.hr.applications.decisions"):
        monkeypatch.setattr(f"{module}.send_email_safely", lambda **kwargs: sent.append(kwargs) or True)
    return sent


def _shortlisting_payload(db_session, application) -> dict:
    instance = (
        db_session.query(StageInstance)
        .filter(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.shortlisting,
        )
        .one()
    )
    return instance.payload or {}


def test_hr_picks_the_shortlist_and_everyone_else_is_recorded_as_not(
    client, db_session, hr_admin, make_job, make_user, monkeypatch
):
    sent = _sent(monkeypatch)
    job = make_job(WORKFLOW, title="Ranked Role")
    scores = [91.0, 84.0, 77.0, 55.0, 40.0]
    applications = []
    for i, score in enumerate(scores):
        from app.models.enums import UserRole
        from app.services.applications import create_application_with_stage_instances

        user = make_user(f"rank{i}@arkivetesting.com", UserRole.applicant)
        application = create_application_with_stage_instances(
            db_session, applicant_id=user.id, requisition=job
        )
        _park_on_shortlisting(db_session, application, match_score=score)
        applications.append(application)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        f"/hr/requisitions/{job.id}/shortlist",
        json=pick(applications[0], applications[4]),
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # exactly who HR named -- note the 40.0 pick, which no cutoff would
    # have produced and which is the whole point of naming them
    assert sorted(row["match_score"] for row in body["shortlisted"]) == [40.0, 91.0]
    assert sorted(row["match_score"] for row in body["not_shortlisted"]) == [55.0, 77.0, 84.0]
    assert body["emails_failed"] == 0

    # every one of them heard something, and only two letters exist
    assert len(sent) == 5
    bodies = [m["body"] for m in sent]
    assert sum(LETTERS["shortlisted_letter"] in b for b in bodies) == 2
    assert sum(LETTERS["not_shortlisted_letter"] in b for b in bodies) == 3


def test_shortlisting_nobody_still_writes_to_everybody(
    client, db_session, hr_admin, make_job, make_user, monkeypatch
):
    sent = _sent(monkeypatch)
    job = make_job(WORKFLOW, title="Nobody Picked")
    from app.models.enums import UserRole
    from app.services.applications import create_application_with_stage_instances

    for i, score in enumerate([90.0, 80.0, 70.0, 60.0]):
        user = make_user(f"wide{i}@arkivetesting.com", UserRole.applicant)
        application = create_application_with_stage_instances(
            db_session, applicant_id=user.id, requisition=job
        )
        _park_on_shortlisting(db_session, application, match_score=score)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        f"/hr/requisitions/{job.id}/shortlist",
        json={**LETTERS, "shortlisted_application_ids": []},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["shortlisted"] == []
    assert len(resp.json()["not_shortlisted"]) == 4
    # the whole field still hears back, which is the half that used to
    # get forgotten when this was done one profile at a time
    assert len(sent) == 4


def test_an_unscored_candidate_can_still_be_picked(
    client, db_session, hr_admin, make_job, make_user, monkeypatch
):
    """The cutoff version held these back, because telling someone they
    missed a cut they were never ranked in would have been a lie. With HR
    naming the shortlist there is no cut to miss -- excluding them would
    be the system overruling a choice HR is entitled to make."""
    sent = _sent(monkeypatch)
    job = make_job(WORKFLOW, title="Partly Scored")
    from app.models.enums import UserRole
    from app.services.applications import create_application_with_stage_instances

    scored_user = make_user("scored@arkivetesting.com", UserRole.applicant)
    scored = create_application_with_stage_instances(
        db_session, applicant_id=scored_user.id, requisition=job
    )
    _park_on_shortlisting(db_session, scored, match_score=88.0)

    unscored_user = make_user("unscored@arkivetesting.com", UserRole.applicant)
    unscored = create_application_with_stage_instances(
        db_session, applicant_id=unscored_user.id, requisition=job
    )
    _park_on_shortlisting(db_session, unscored, match_score=None)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    # HR picks the unscored one and not the 88%
    resp = client.post(
        f"/hr/requisitions/{job.id}/shortlist",
        json=pick(unscored),
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [row["application_id"] for row in body["shortlisted"]] == [unscored.id]
    assert [row["application_id"] for row in body["not_shortlisted"]] == [scored.id]
    # an unscored candidate carries no rank, since there is nothing to rank
    assert body["shortlisted"][0]["rank"] is None
    assert len(sent) == 2


def test_the_ones_below_the_line_stay_active_rather_than_rejected(
    client, db_session, hr_admin, make_job, make_user, monkeypatch
):
    """They can wait or look elsewhere, and HR can still promote one if
    somebody above the line drops out."""
    _sent(monkeypatch)
    job = make_job(WORKFLOW, title="Bench Kept")
    from app.models.enums import UserRole
    from app.services.applications import create_application_with_stage_instances

    below = above = None
    for i, score in enumerate([95.0, 30.0]):
        user = make_user(f"bench{i}@arkivetesting.com", UserRole.applicant)
        application = create_application_with_stage_instances(
            db_session, applicant_id=user.id, requisition=job
        )
        _park_on_shortlisting(db_session, application, match_score=score)
        if score == 30.0:
            below = application
        else:
            above = application
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    client.post(
        f"/hr/requisitions/{job.id}/shortlist",
        json={**LETTERS, "shortlisted_application_ids": [above.id]},
        headers=headers,
    )

    db_session.refresh(below)
    assert below.status == ApplicationStatus.active
    assert below.current_stage == StageType.shortlisting
    assert _shortlisting_payload(db_session, below)["outcome"] == "not_shortlisted"
    # nothing to confirm -- they were not shortlisted
    assert "acceptance" not in _shortlisting_payload(db_session, below)


def test_shortlisting_asks_for_a_confirmation_and_accepting_advances(
    client, db_session, hr_admin, applicant, make_job, make_application, monkeypatch
):
    _sent(monkeypatch)
    job = make_job(WORKFLOW, title="Confirmable Role")
    application = make_application(job)
    _park_on_shortlisting(db_session, application, match_score=99.0)
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    client.post(
        f"/hr/requisitions/{job.id}/shortlist",
        json=pick(application),
        headers=hr_headers,
    )

    # the applicant is asked, and is still sitting on shortlisting
    applicant_headers = auth_headers(client, "applicant-test@arkivetesting.com")
    detail = client.get(f"/applicant/applications/{application.id}", headers=applicant_headers).json()
    assert detail["current_stage"] == "shortlisting"
    assert detail["shortlisting_acceptance"]["response"] is None

    resp = client.post(
        f"/applicant/applications/{application.id}/shortlisting/accept",
        headers=applicant_headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["current_stage"] == "examination"
    assert resp.json()["shortlisting_acceptance"]["response"] == "accepted"


def test_declining_withdraws_the_application(
    client, db_session, hr_admin, applicant, make_job, make_application, monkeypatch
):
    """Same terminal state as Cancel Application -- out by their own
    choice, DFA frozen."""
    _sent(monkeypatch)
    job = make_job(WORKFLOW, title="Declinable Role")
    application = make_application(job)
    _park_on_shortlisting(db_session, application, match_score=99.0)
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    client.post(
        f"/hr/requisitions/{job.id}/shortlist",
        json=pick(application),
        headers=hr_headers,
    )
    applicant_headers = auth_headers(client, "applicant-test@arkivetesting.com")

    resp = client.post(
        f"/applicant/applications/{application.id}/shortlisting/decline",
        headers=applicant_headers,
    )

    assert resp.status_code == 200, resp.text
    db_session.refresh(application)
    assert application.status == ApplicationStatus.withdrawn
    assert application.current_stage == StageType.shortlisting


def test_a_candidate_who_was_not_shortlisted_has_nothing_to_confirm(
    client, db_session, hr_admin, applicant, make_job, make_application, monkeypatch
):
    _sent(monkeypatch)
    job = make_job(WORKFLOW, title="Below The Line")
    application = make_application(job)
    _park_on_shortlisting(db_session, application, match_score=10.0)
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    client.post(
        f"/hr/requisitions/{job.id}/shortlist",
        json=pick(application),
        headers=hr_headers,
    )
    # cutoff 1 with a single candidate shortlists them, so force the
    # other outcome directly -- what is under test is the applicant route
    shortlisting.record_outcome(
        db_session,
        instance=db_session.query(StageInstance)
        .filter(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.shortlisting,
        )
        .one(),
        outcome="not_shortlisted",
    )
    db_session.flush()
    applicant_headers = auth_headers(client, "applicant-test@arkivetesting.com")

    resp = client.post(
        f"/applicant/applications/{application.id}/shortlisting/accept",
        headers=applicant_headers,
    )

    assert resp.status_code == 409, resp.text
    assert "not been shortlisted" in resp.json()["detail"]


def test_answering_twice_is_refused(
    client, db_session, hr_admin, applicant, make_job, make_application, monkeypatch
):
    _sent(monkeypatch)
    job = make_job(WORKFLOW, title="Answer Once")
    application = make_application(job)
    _park_on_shortlisting(db_session, application, match_score=99.0)
    hr_headers = auth_headers(client, "hr-test@arkivetesting.com")
    client.post(
        f"/hr/requisitions/{job.id}/shortlist",
        json=pick(application),
        headers=hr_headers,
    )
    applicant_headers = auth_headers(client, "applicant-test@arkivetesting.com")
    client.post(
        f"/applicant/applications/{application.id}/shortlisting/decline",
        headers=applicant_headers,
    )

    resp = client.post(
        f"/applicant/applications/{application.id}/shortlisting/decline",
        headers=applicant_headers,
    )

    # withdrawn, so the stage guard catches it first -- either way it is
    # refused rather than recorded twice
    assert resp.status_code == 409, resp.text


def test_a_blank_letter_is_refused_before_anything_is_recorded(
    client, db_session, hr_admin, make_job, make_application, monkeypatch
):
    sent = _sent(monkeypatch)
    job = make_job(WORKFLOW, title="No Blank Sends")
    application = make_application(job)
    _park_on_shortlisting(db_session, application, match_score=99.0)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        f"/hr/requisitions/{job.id}/shortlist",
        json={**pick(application), "shortlisted_letter": "   "},
        headers=headers,
    )

    assert resp.status_code == 422, resp.text
    assert sent == []
    assert _shortlisting_payload(db_session, application).get("outcome") is None


def test_a_job_without_a_shortlisting_stage_is_refused(
    client, db_session, hr_admin, make_job
):
    job = make_job(["document_upload", "final_decision"], title="No Shortlisting Here")
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        f"/hr/requisitions/{job.id}/shortlist",
        json={**LETTERS, "shortlisted_application_ids": []},
        headers=headers,
    )

    assert resp.status_code == 409, resp.text
    assert "no Shortlisting stage" in resp.json()["detail"]


def test_a_failing_mail_server_still_records_the_decision(
    client, db_session, hr_admin, make_job, make_application, monkeypatch
):
    """The outcomes are the decision; the letters are how it is
    announced. A mail server having a bad minute must not leave half a
    shortlist recorded and half not."""
    monkeypatch.setattr("app.api.hr.applications.decisions.send_email_safely", lambda **kwargs: False)
    job = make_job(WORKFLOW, title="Mail Down")
    application = make_application(job)
    _park_on_shortlisting(db_session, application, match_score=99.0)
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        f"/hr/requisitions/{job.id}/shortlist",
        json=pick(application),
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["emails_failed"] == 1
    assert resp.json()["shortlisted"][0]["emailed"] is False
    assert _shortlisting_payload(db_session, application)["outcome"] == "shortlisted"


def test_only_hr_can_run_a_bulk_shortlist(client, hr_admin, applicant, make_job):
    job = make_job(WORKFLOW, title="HR Only")
    headers = auth_headers(client, "applicant-test@arkivetesting.com")

    resp = client.post(
        f"/hr/requisitions/{job.id}/shortlist",
        json={**LETTERS, "shortlisted_application_ids": []},
        headers=headers,
    )

    assert resp.status_code == 403


def _decide(db_session, application, outcome):
    shortlisting.record_outcome(
        db_session,
        instance=db_session.query(StageInstance)
        .filter(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.shortlisting,
        )
        .one(),
        outcome=outcome,
    )
    db_session.flush()


def test_a_decision_made_on_the_profile_is_left_alone(
    client, db_session, hr_admin, make_job, make_user, monkeypatch
):
    """HR marked this candidate on their own profile. That call stands:
    they are not in the pick list, not re-decided, and not written to.
    Remaking it in bulk would mean a decision changing without anyone
    opening the record it was made on."""
    sent = _sent(monkeypatch)
    job = make_job(WORKFLOW, title="Decided On Profile")
    from app.models.enums import UserRole
    from app.services.applications import create_application_with_stage_instances

    apps = []
    for i, score in enumerate([90.0, 57.7]):
        user = make_user(f"held{i}@arkivetesting.com", UserRole.applicant)
        a = create_application_with_stage_instances(
            db_session, applicant_id=user.id, requisition=job
        )
        _park_on_shortlisting(db_session, a, match_score=score)
        apps.append(a)
    waiting, settled = apps
    _decide(db_session, settled, "not_shortlisted")
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        f"/hr/requisitions/{job.id}/shortlist",
        json=pick(waiting),
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [row["application_id"] for row in body["shortlisted"]] == [waiting.id]
    assert body["not_shortlisted"] == []
    assert [row["application_id"] for row in body["already_decided"]] == [settled.id]
    assert body["already_decided"][0]["outcome"] == "not_shortlisted"

    # untouched, and nothing sent to them
    assert _shortlisting_payload(db_session, settled)["outcome"] == "not_shortlisted"
    assert len(sent) == 1
    assert sent[0]["to"] != "held1@arkivetesting.com"


def test_naming_an_already_decided_candidate_is_refused(
    client, db_session, hr_admin, make_job, make_user, monkeypatch
):
    """An id outside the pool means the browser and the database
    disagree about who is still waiting, so the whole request is refused
    rather than partly applied."""
    sent = _sent(monkeypatch)
    job = make_job(WORKFLOW, title="Named But Decided")
    from app.models.enums import UserRole
    from app.services.applications import create_application_with_stage_instances

    apps = []
    for i, score in enumerate([80.0, 57.7]):
        user = make_user(f"named{i}@arkivetesting.com", UserRole.applicant)
        a = create_application_with_stage_instances(
            db_session, applicant_id=user.id, requisition=job
        )
        _park_on_shortlisting(db_session, a, match_score=score)
        apps.append(a)
    waiting, settled = apps
    _decide(db_session, settled, "shortlisted")
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        f"/hr/requisitions/{job.id}/shortlist",
        json={**LETTERS, "shortlisted_application_ids": [settled.id]},
        headers=headers,
    )

    assert resp.status_code == 409, resp.text
    assert "already have a shortlisting decision" in resp.json()["detail"]
    # nothing partly applied: the waiting candidate is untouched too
    assert _shortlisting_payload(db_session, waiting).get("outcome") is None
    assert sent == []


def test_a_field_that_is_entirely_decided_has_nothing_to_do(
    client, db_session, hr_admin, applicant, make_job, make_application, monkeypatch
):
    sent = _sent(monkeypatch)
    job = make_job(WORKFLOW, title="All Decided")
    application = make_application(job)
    _park_on_shortlisting(db_session, application, match_score=57.7)
    _decide(db_session, application, "not_shortlisted")
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        f"/hr/requisitions/{job.id}/shortlist",
        json={**LETTERS, "shortlisted_application_ids": []},
        headers=headers,
    )

    assert resp.status_code == 409, resp.text
    assert "already has a decision recorded" in resp.json()["detail"]
    assert _shortlisting_payload(db_session, application)["outcome"] == "not_shortlisted"
    assert sent == []


def test_the_pipeline_list_shows_a_recorded_shortlisting_outcome(
    client, db_session, hr_admin, applicant, make_job, make_application
):
    """The dialog's preview is built from this list, so the decision has
    to be on the row or the preview cannot show it."""
    job = make_job(WORKFLOW, title="Outcome On The Row")
    application = make_application(job)
    _park_on_shortlisting(db_session, application, match_score=57.7)
    shortlisting.record_outcome(
        db_session,
        instance=db_session.query(StageInstance)
        .filter(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.shortlisting,
        )
        .one(),
        outcome="not_shortlisted",
    )
    db_session.flush()
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    rows = client.get("/hr/applications", headers=headers).json()
    row = next(r for r in rows if r["id"] == application.id)

    assert row["shortlisting_outcome"] == "not_shortlisted"


def _shortlist_on_the_profile(client, application):
    return client.patch(
        f"/hr/applications/{application.id}/shortlisting-result",
        json={"stage_type": "shortlisting", "outcome": "shortlisted"},
        headers=auth_headers(client, "hr-test@arkivetesting.com"),
    )


def test_the_shortlisted_email_names_the_jobs_own_next_stage(
    client, db_session, hr_admin, make_job, make_application, monkeypatch
):
    """Shortlisting on the profile emails the applicant. It names the
    stage this job really goes to next, with HR's own name for it, and
    promises no exam booking: the applicant picks their own session, and
    not every workflow has an exam after Shortlisting."""
    sent = _sent(monkeypatch)
    job = make_job(
        ["document_upload", "skill_matching", "shortlisting", "interview_round_1", "final_decision"],
        title="Panel Role",
    )
    job.interview_round_labels = {"interview_round_1": "Panel Interview"}
    application = make_application(job)
    _park_on_shortlisting(db_session, application, match_score=80.0)

    resp = _shortlist_on_the_profile(client, application)

    assert resp.status_code == 200, resp.text
    assert len(sent) == 1
    body = sent[0]["body"]
    assert "you've been shortlisted for Panel Role, and your next stage is Panel Interview." in body
    assert "confirm that you'd still like to go ahead. HR will then arrange the next step with you." in body
    assert "examination" not in body.lower()


def test_the_shortlisted_email_names_an_exam_when_one_comes_next(
    client, db_session, hr_admin, make_job, make_application, monkeypatch
):
    sent = _sent(monkeypatch)
    job = make_job(
        ["document_upload", "skill_matching", "shortlisting", "examination_1", "final_decision"],
        title="Exam Role",
    )
    application = make_application(job)
    _park_on_shortlisting(db_session, application, match_score=80.0)

    resp = _shortlist_on_the_profile(client, application)

    assert resp.status_code == 200, resp.text
    assert "you've been shortlisted for Exam Role, and your next stage is Examination." in sent[0]["body"]
    assert "booked" not in sent[0]["body"]


def test_the_shortlisted_notice_asks_for_a_confirmation(
    client, db_session, hr_admin, applicant, make_job, make_application, monkeypatch
):
    """Shortlisting on the profile and the bulk shortlist send the same
    in-app words, since either way the applicant owes a confirmation."""
    _sent(monkeypatch)
    application = make_application(make_job(WORKFLOW, title="Notice Role"))
    _park_on_shortlisting(db_session, application, match_score=80.0)

    resp = _shortlist_on_the_profile(client, application)

    assert resp.status_code == 200, resp.text
    notice = db_session.scalar(select(Notification).where(Notification.user_id == applicant.id))
    assert notice.title == "You've been shortlisted"
    assert notice.message == "You've been shortlisted for Notice Role. Please confirm to continue."
