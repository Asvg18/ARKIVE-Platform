"""Coverage for the offer-response flow.

The applicant answers an offer rather than only reading that HR marked
them hired. These tests pin four things: a deadline set on hire,
accepting answers it, declining withdraws and tells HR, and a read
after the window closed does the same on its own.

The last one is the interesting case, since expiry is deliberately lazy
-- evaluated on read, not by a scheduled job (see services.offers for
why). So "time passes" is simulated by rewriting the stored deadline
into the past and issuing an ordinary GET, exactly the path a real
lapse takes."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.enums import ApplicationStatus, StageType, UserRole
from app.models.notification import Notification
from app.models.stage_instance import StageInstance
from app.models.user import User
from app.services import offers
from tests.conftest import auth_headers

WORKFLOW = ["document_upload", "skill_matching", "final_decision", "onboarding"]


def _hire(client, hr_admin, application_id: int) -> dict:
    """Mark an application hired through HR's real endpoint, rather than
    setting the column directly — the offer window is opened by that
    endpoint, so a test that shortcut it would be testing nothing."""
    resp = client.patch(
        f"/hr/applications/{application_id}/status",
        json={
            "status": "hired",
            # These applications are deliberately bare, so the
            # incomplete-record gate would otherwise refuse. Overriding
            # it is the documented escape hatch and needs a reason.
            "acknowledged_incomplete": True,
            "reason": "Offer-response test fixture.",
        },
        headers=auth_headers(client, hr_admin.email),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _offer_of(client, applicant, application_id: int) -> dict | None:
    resp = client.get(
        f"/applicant/applications/{application_id}", headers=auth_headers(client, applicant.email)
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["offer"]


def _rewind_deadline(db_session, application_id: int, *, days: int) -> None:
    """Move the stored deadline `days` into the past. Reassigns the
    payload rather than mutating it in place — a plain JSON column has no
    mutation tracking, so an in-place edit would never be flushed."""
    instance = db_session.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application_id,
            StageInstance.stage_type == StageType.final_decision,
        )
    )
    payload = dict(instance.payload or {})
    offer = dict(payload["offer"])
    offer["deadline"] = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    payload["offer"] = offer
    instance.payload = payload
    db_session.flush()


def _hr_notifications(db_session) -> list[str]:
    hr_ids = [u.id for u in db_session.scalars(select(User).where(User.role == UserRole.hr_admin))]
    return [
        n.message
        for n in db_session.scalars(select(Notification).where(Notification.user_id.in_(hr_ids)))
    ]


# --- The deadline -----------------------------------------------------


def test_hiring_opens_a_seven_day_offer_window(client, hr_admin, applicant, make_job, make_application, db_session):
    application = make_application(make_job(WORKFLOW))
    db_session.flush()
    _hire(client, hr_admin, application.id)

    offer = _offer_of(client, applicant, application.id)

    assert offer is not None
    assert offer["window_days"] == offers.OFFER_RESPONSE_WINDOW_DAYS == 7
    assert offer["response"] is None
    deadline = datetime.fromisoformat(offer["deadline"])
    expected = datetime.now(timezone.utc) + timedelta(days=7)
    assert abs((deadline - expected).total_seconds()) < 120


def test_an_application_that_was_never_hired_has_no_offer(client, applicant, make_job, make_application, db_session):
    application = make_application(make_job(WORKFLOW))
    db_session.flush()

    assert _offer_of(client, applicant, application.id) is None


def test_reopening_a_hire_clears_the_offer(client, hr_admin, applicant, make_job, make_application, db_session):
    """A stale window left on a reopened application would let the lazy
    expiry check withdraw someone who is no longer on offer at all."""
    application = make_application(make_job(WORKFLOW))
    db_session.flush()
    _hire(client, hr_admin, application.id)

    client.patch(
        f"/hr/applications/{application.id}/status",
        json={"status": "active", "reason": "Reopened."},
        headers=auth_headers(client, hr_admin.email),
    )

    assert _offer_of(client, applicant, application.id) is None


# --- Accepting --------------------------------------------------------


def test_accepting_records_the_response_and_keeps_the_hire(client, hr_admin, applicant, make_job, make_application, db_session):
    application = make_application(make_job(WORKFLOW))
    db_session.flush()
    _hire(client, hr_admin, application.id)

    resp = client.post(
        f"/applicant/applications/{application.id}/offer/accept",
        headers=auth_headers(client, applicant.email),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "hired"
    assert body["offer"]["response"] == "accepted"
    assert body["offer"]["responded_at"] is not None


def test_an_offer_cannot_be_answered_twice(client, hr_admin, applicant, make_job, make_application, db_session):
    application = make_application(make_job(WORKFLOW))
    db_session.flush()
    _hire(client, hr_admin, application.id)
    headers = auth_headers(client, applicant.email)
    client.post(f"/applicant/applications/{application.id}/offer/accept", headers=headers)

    resp = client.post(f"/applicant/applications/{application.id}/offer/accept", headers=headers)

    assert resp.status_code == 409, resp.text


def test_accepting_an_offer_that_does_not_exist_is_refused(client, applicant, make_job, make_application, db_session):
    application = make_application(make_job(WORKFLOW))
    db_session.flush()

    resp = client.post(
        f"/applicant/applications/{application.id}/offer/accept",
        headers=auth_headers(client, applicant.email),
    )

    assert resp.status_code == 409, resp.text


# --- Declining --------------------------------------------------------


def test_declining_withdraws_the_application_and_notifies_hr(client, hr_admin, applicant, make_job, make_application, db_session):
    """Round-2 item 1b: before this, an accepted applicant had no way to
    say no — the "Cancel Application" action renders only while the
    status is still active."""
    application = make_application(make_job(WORKFLOW))
    db_session.flush()
    _hire(client, hr_admin, application.id)

    resp = client.post(
        f"/applicant/applications/{application.id}/offer/decline",
        json={"reason": "Accepted another role."},
        headers=auth_headers(client, applicant.email),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "withdrawn"
    assert body["offer"]["response"] == "declined"
    assert any("declined the offer" in m for m in _hr_notifications(db_session))


def test_declining_freezes_the_dfa(client, hr_admin, applicant, make_job, make_application, db_session):
    """A declined application is withdrawn, and withdrawn freezes stage
    progress the same way it always has — see
    app.services.applications.transition_application_stage."""
    application = make_application(make_job(WORKFLOW))
    db_session.flush()
    _hire(client, hr_admin, application.id)
    client.post(
        f"/applicant/applications/{application.id}/offer/decline",
        json={},
        headers=auth_headers(client, applicant.email),
    )

    resp = client.post(
        f"/applications/{application.id}/transition",
        json={"target_stage": "onboarding"},
        headers=auth_headers(client, hr_admin.email),
    )

    # 422 is what an illegal transition has always returned; the point
    # here is the reason, which is the withdrawn freeze rather than a
    # sequence complaint.
    assert resp.status_code == 422, resp.text
    assert "withdrawn" in resp.json()["detail"]


# --- Expiry (lazy, on read) -------------------------------------------


def test_a_read_after_the_deadline_auto_withdraws_and_notifies_hr(client, hr_admin, applicant, make_job, make_application, db_session):
    """Decision R1: the window closing auto-withdraws and tells HR."""
    application = make_application(make_job(WORKFLOW))
    db_session.flush()
    _hire(client, hr_admin, application.id)
    _rewind_deadline(db_session, application.id, days=1)

    resp = client.get(
        f"/applicant/applications/{application.id}", headers=auth_headers(client, applicant.email)
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "withdrawn"
    assert body["offer"]["response"] == "expired"
    assert any("did not respond within 7 days" in m for m in _hr_notifications(db_session))


def test_hrs_own_board_expires_a_lapsed_offer_too(client, hr_admin, applicant, make_job, make_application, db_session):
    application = make_application(make_job(WORKFLOW))
    db_session.flush()
    _hire(client, hr_admin, application.id)
    _rewind_deadline(db_session, application.id, days=1)

    resp = client.get("/hr/applications", headers=auth_headers(client, hr_admin.email))

    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json() if r["id"] == application.id)
    assert row["status"] == "withdrawn"


def test_responding_after_the_deadline_is_refused(client, hr_admin, applicant, make_job, make_application, db_session):
    """An offer answered one second after it lapsed is not an answer —
    letting it through would resurrect an application the clock closed."""
    application = make_application(make_job(WORKFLOW))
    db_session.flush()
    _hire(client, hr_admin, application.id)
    _rewind_deadline(db_session, application.id, days=1)

    resp = client.post(
        f"/applicant/applications/{application.id}/offer/accept",
        headers=auth_headers(client, applicant.email),
    )

    assert resp.status_code == 409, resp.text
    assert "expired" in resp.json()["detail"]


def test_a_legacy_hire_with_no_deadline_is_never_auto_withdrawn(client, hr_admin, applicant, make_job, make_application, db_session):
    """Every application hired before offers existed carries no deadline.
    Inventing a retroactive one would auto-withdraw a real hire on the
    next page load — so absent deadline means no window at all."""
    application = make_application(make_job(WORKFLOW))
    db_session.flush()
    _hire(client, hr_admin, application.id)
    offers.clear_offer(db_session, application)
    db_session.flush()

    resp = client.get(
        f"/applicant/applications/{application.id}", headers=auth_headers(client, applicant.email)
    )

    assert resp.json()["status"] == "hired"
    assert resp.json()["offer"] is None


def test_an_already_declined_offer_is_not_expired_again(client, hr_admin, applicant, make_job, make_application, db_session):
    """Expiry is narrow by design: only an application that is currently
    hired and carries an *unanswered* deadline can lapse."""
    application = make_application(make_job(WORKFLOW))
    db_session.flush()
    _hire(client, hr_admin, application.id)
    headers = auth_headers(client, applicant.email)
    client.post(f"/applicant/applications/{application.id}/offer/decline", json={}, headers=headers)
    _rewind_deadline(db_session, application.id, days=1)

    body = client.get(f"/applicant/applications/{application.id}", headers=headers).json()

    assert body["status"] == "withdrawn"
    assert body["offer"]["response"] == "declined"


# --- The onboarding checklist gate ------------------------------------


def test_the_onboarding_checklist_waits_for_the_offer_to_be_answered(client, hr_admin, applicant, make_job, make_application, db_session):
    """The first checklist item is "sign and return the offer letter" —
    not a thing to be ticking while the offer itself is unanswered."""
    application = make_application(make_job(WORKFLOW))
    db_session.flush()
    application.current_stage = StageType.onboarding
    db_session.flush()
    _hire(client, hr_admin, application.id)

    resp = client.patch(
        f"/applicant/applications/{application.id}/onboarding",
        json={"checklist": {"signed_offer": True}},
        headers=auth_headers(client, applicant.email),
    )

    assert resp.status_code == 409, resp.text


def test_accepting_unlocks_the_onboarding_checklist(client, hr_admin, applicant, make_job, make_application, db_session):
    application = make_application(make_job(WORKFLOW))
    db_session.flush()
    application.current_stage = StageType.onboarding
    db_session.flush()
    _hire(client, hr_admin, application.id)
    headers = auth_headers(client, applicant.email)
    client.post(f"/applicant/applications/{application.id}/offer/accept", headers=headers)

    resp = client.patch(
        f"/applicant/applications/{application.id}/onboarding",
        json={"checklist": {"signed_offer": True}},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    assert application.status == ApplicationStatus.hired
