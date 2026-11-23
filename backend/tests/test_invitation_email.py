"""Invitations by email (28 Sep 2026): each invitation records whether its
link actually went out, User Management can ask whether this copy of
ARKIVE can send email at all, and an invitation can be sent again.

Before this, the only sign an invitation had not been emailed was a
sentence beside a link on the screen -- and the same link box showed
when it *had* been, so an emailed invitation looked like a plain link.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.infra.config import settings
from app.models.enums import UserRole
from app.models.invite import Invite
from app.services import staff_accounts
from tests.conftest import TEST_PASSWORD, auth_headers


@pytest.fixture()
def mail_works(monkeypatch):
    """A mail server that accepts everything, recording what it was given."""
    sent: list[dict] = []
    monkeypatch.setattr(staff_accounts, "send_email_safely", lambda **kw: sent.append(kw) or True)
    return sent


def _invite(client, headers, email="invitee@arkivetesting.com", role="evaluator"):
    resp = client.post("/hr/invites", json={"email": email, "role": role}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _listed(client, headers, invite_id):
    return next(i for i in client.get("/hr/invites", headers=headers).json() if i["id"] == invite_id)


def test_an_emailed_invitation_records_when_it_went_out(client, hr_admin, mail_works):
    headers = auth_headers(client, hr_admin.email)

    created = _invite(client, headers)

    assert created["emailed"] is True
    assert created["emailed_at"] is not None
    assert _listed(client, headers, created["id"])["emailed_at"] is not None
    assert mail_works[0]["to"] == "invitee@arkivetesting.com"


def test_an_invitation_that_could_not_be_emailed_says_so(client, hr_admin):
    """Mail is blanked in the suite: the invitation still exists, and says
    it was never emailed rather than looking like one that was."""
    headers = auth_headers(client, hr_admin.email)

    created = _invite(client, headers)

    assert created["emailed"] is False
    assert created["emailed_at"] is None
    assert created["token"], "the link must still come back to send by hand"


def test_resending_emails_a_fresh_link_and_retires_the_old_one(client, hr_admin, mail_works):
    headers = auth_headers(client, hr_admin.email)
    first = _invite(client, headers)

    resent = client.post(f"/hr/invites/{first['id']}/resend", headers=headers)

    assert resent.status_code == 200, resent.text
    body = resent.json()
    assert body["emailed"] is True
    assert body["token"] != first["token"]
    assert len(mail_works) == 2
    assert f"/accept-invite/{body['token']}" in mail_works[1]["body"]
    # only the newest email's link is live
    assert client.get(f"/invites/{first['token']}").status_code == 404
    assert client.get(f"/invites/{body['token']}").json()["status"] == "pending"


def test_resending_after_mail_is_set_up_marks_it_emailed(client, hr_admin, monkeypatch):
    """The case this exists for: the first attempt found no mail server."""
    headers = auth_headers(client, hr_admin.email)
    first = _invite(client, headers)
    assert first["emailed_at"] is None

    monkeypatch.setattr(staff_accounts, "send_email_safely", lambda **kw: True)
    resent = client.post(f"/hr/invites/{first['id']}/resend", headers=headers).json()

    assert resent["emailed"] is True
    assert _listed(client, headers, first["id"])["emailed_at"] is not None


def test_an_expired_invitation_can_be_sent_again(client, hr_admin, db_session, mail_works):
    headers = auth_headers(client, hr_admin.email)
    created = _invite(client, headers)
    invite = db_session.get(Invite, created["id"])
    invite.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.flush()
    assert _listed(client, headers, created["id"])["status"] == "expired"

    resent = client.post(f"/hr/invites/{created['id']}/resend", headers=headers)

    assert resent.status_code == 200, resent.text
    assert resent.json()["status"] == "pending"


def test_an_accepted_or_revoked_invitation_is_not_sent_again(client, hr_admin, mail_works):
    headers = auth_headers(client, hr_admin.email)
    accepted = _invite(client, headers, email="took-it@arkivetesting.com")
    client.post(f"/invites/{accepted['token']}/accept", json={"full_name": "Took It", "password": TEST_PASSWORD})
    revoked = _invite(client, headers, email="changed-mind@arkivetesting.com")
    client.post(f"/hr/invites/{revoked['id']}/revoke", headers=headers)

    assert client.post(f"/hr/invites/{accepted['id']}/resend", headers=headers).status_code == 409
    assert client.post(f"/hr/invites/{revoked['id']}/resend", headers=headers).status_code == 409


def test_resending_is_held_to_the_rule_a_new_invitation_is(client, hr_admin, make_user, mail_works):
    headers = auth_headers(client, hr_admin.email)
    became_account = _invite(client, headers, email="signed-up-meanwhile@arkivetesting.com")
    make_user("signed-up-meanwhile@arkivetesting.com", UserRole.applicant)

    assert client.post(f"/hr/invites/{became_account['id']}/resend", headers=headers).status_code == 409


def test_user_management_is_told_when_this_copy_cannot_email(client, hr_admin):
    resp = client.get("/hr/invitation-email", headers=auth_headers(client, hr_admin.email))
    assert resp.json() == {"configured": False, "sender": None}


def test_user_management_is_told_who_invitations_come_from(client, hr_admin, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_username", "login-name")
    monkeypatch.setattr(settings, "smtp_password", "never-shown")
    monkeypatch.setattr(settings, "smtp_from_email", "hiring@example.com")

    resp = client.get("/hr/invitation-email", headers=auth_headers(client, hr_admin.email))

    assert resp.json() == {"configured": True, "sender": "hiring@example.com"}
    assert "never-shown" not in resp.text


def test_the_setup_step_records_its_email_too(db_session, mail_works):
    """The first super admin's invitation goes through the same code."""
    from sqlalchemy import select, update

    from app.models.user import User
    from scripts.create_first_admin import DONE, run

    db_session.execute(update(User).values(is_super_admin=False))
    db_session.flush()

    assert run(db_session, "setup-mailed@arkivetesting.com", say=lambda _line: None) == DONE

    invite = db_session.scalar(select(Invite).where(Invite.email == "setup-mailed@arkivetesting.com"))
    assert invite.emailed_at is not None
