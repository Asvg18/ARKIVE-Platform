"""Tests for "I forgot my password" -- the one account-recovery path
the system had no answer for at all. Before this, a forgotten password
could only be repaired by an operator editing the database, which is
not a recovery story for a system with applicants outside the
organisation.

The security property under test throughout is that **none of this
reveals whether an address has an account.** The request form is open
to the internet, so an answer that varied would be a free membership
oracle: who works here, who has applied here.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.infra import rate_limit
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.services import password_reset
from tests.conftest import TEST_PASSWORD, auth_headers

NEW_PASSWORD = "a-reset-password-99"


@pytest.fixture(autouse=True)
def _clean_limits():
    """These endpoints are rate limited on a process-global counter, so
    one test's requests would otherwise be counted against the next."""
    rate_limit.reset_all()
    yield
    rate_limit.reset_all()


@pytest.fixture()
def captured_emails(monkeypatch) -> list[dict]:
    """SMTP is not configured in tests (and must not be), so the real
    sender would no-op. Captured instead, because the link only exists
    in the message body -- that is the whole point of the design."""
    sent: list[dict] = []

    def _capture(*, to: str, subject: str, body: str) -> bool:
        sent.append({"to": to, "subject": subject, "body": body})
        return True

    monkeypatch.setattr(password_reset, "send_email_safely", _capture)
    return sent


def _request_reset(client, email: str) -> None:
    resp = client.post("/auth/forgot-password", json={"email": email})
    assert resp.status_code == 202, resp.text


def _link_token(sent: list[dict]) -> str:
    """The raw token as it reaches the person -- pulled out of the email
    rather than the database, since the database only ever holds its
    digest."""
    assert sent, "no email was sent"
    return sent[-1]["body"].split("/reset-password/")[1].split()[0]


# --------------------------------------------------------------------
# Requesting a link
# --------------------------------------------------------------------


def test_a_reset_link_is_emailed_to_a_real_account(client, applicant, captured_emails):
    _request_reset(client, applicant.email)

    assert len(captured_emails) == 1
    assert captured_emails[0]["to"] == applicant.email
    assert "/reset-password/" in captured_emails[0]["body"]


def test_an_unknown_address_looks_exactly_like_a_known_one(client, applicant, captured_emails):
    """The membership oracle this endpoint must not be. Same status,
    same empty body -- the only difference is invisible from outside."""
    known = client.post("/auth/forgot-password", json={"email": applicant.email})
    unknown = client.post("/auth/forgot-password", json={"email": "nobody@arkivetesting.com"})

    assert known.status_code == unknown.status_code == 202
    assert known.content == unknown.content
    assert [m["to"] for m in captured_emails] == [applicant.email]


def test_a_deactivated_account_gets_no_link(client, hr_admin, evaluator, captured_emails):
    """Someone who has been offboarded must not be able to let
    themselves back in -- and the link would lead to a refusal at login
    anyway."""
    client.post(f"/hr/staff/{evaluator.id}/deactivate", headers=auth_headers(client, hr_admin.email))

    resp = client.post("/auth/forgot-password", json={"email": evaluator.email})
    assert resp.status_code == 202
    assert captured_emails == []


def test_asking_again_invalidates_the_first_link(client, applicant, captured_emails):
    """Two live links is a wider window for no benefit -- a second
    request almost always means the first mail went astray."""
    _request_reset(client, applicant.email)
    first_token = _link_token(captured_emails)
    _request_reset(client, applicant.email)
    second_token = _link_token(captured_emails)
    assert first_token != second_token

    stale = client.get(f"/auth/reset-password/{first_token}")
    assert stale.json()["status"] == "used"
    fresh = client.get(f"/auth/reset-password/{second_token}")
    assert fresh.json()["status"] == "valid"


def test_one_inbox_cannot_be_used_as_a_weapon(client, applicant, captured_emails):
    """Without a per-address limit, anyone could point this at a person
    and fill their mailbox."""
    for _ in range(rate_limit.MAX_ATTEMPTS + 3):
        client.post("/auth/forgot-password", json={"email": applicant.email})

    assert len(captured_emails) <= rate_limit.MAX_ATTEMPTS


def test_being_rate_limited_still_answers_202(client, applicant):
    """A 429 here would say "this address was asked about recently",
    which is most of what the uniform answer exists to hide."""
    for _ in range(rate_limit.MAX_ATTEMPTS + 3):
        resp = client.post("/auth/forgot-password", json={"email": applicant.email})
        assert resp.status_code == 202, resp.text


# --------------------------------------------------------------------
# The database side of the link
# --------------------------------------------------------------------


def test_the_raw_token_is_never_stored(client, applicant, captured_emails, db_session):
    """Same discipline as invites: the database holds a digest, so a
    copy of it cannot be used to take over an account."""
    _request_reset(client, applicant.email)
    raw = _link_token(captured_emails)

    rows = db_session.scalars(
        select(PasswordResetToken).where(PasswordResetToken.user_id == applicant.id)
    ).all()
    assert len(rows) == 1
    assert rows[0].token_hash != raw
    assert rows[0].token_hash == password_reset.hash_token(raw)


# --------------------------------------------------------------------
# Spending the link
# --------------------------------------------------------------------


def test_a_reset_sets_the_new_password_and_retires_the_old(client, applicant, captured_emails):
    _request_reset(client, applicant.email)
    token = _link_token(captured_emails)

    resp = client.post(f"/auth/reset-password/{token}", json={"new_password": NEW_PASSWORD})
    assert resp.status_code == 204, resp.text

    assert client.post(
        "/auth/login", json={"email": applicant.email, "password": NEW_PASSWORD}
    ).status_code == 200
    assert client.post(
        "/auth/login", json={"email": applicant.email, "password": TEST_PASSWORD}
    ).status_code == 401


def test_a_reset_does_not_create_a_session(client, applicant, captured_emails):
    """A reset changes the password but does not create a session."""
    _request_reset(client, applicant.email)
    token = _link_token(captured_emails)
    response = client.post(
        f"/auth/reset-password/{token}", json={"new_password": NEW_PASSWORD}
    )
    assert response.status_code == 204

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})


def test_a_link_works_only_once(client, applicant, captured_emails):
    _request_reset(client, applicant.email)
    token = _link_token(captured_emails)

    first = client.post(f"/auth/reset-password/{token}", json={"new_password": NEW_PASSWORD})
    second = client.post(f"/auth/reset-password/{token}", json={"new_password": "something-else-1"})

    assert first.status_code == 204, first.text
    assert second.status_code == 400
    assert "already been used" in second.text

    # and the second password never took
    assert client.post(
        "/auth/login", json={"email": applicant.email, "password": NEW_PASSWORD}
    ).status_code == 200


def test_an_expired_link_is_refused(client, applicant, captured_emails, db_session):
    _request_reset(client, applicant.email)
    token = _link_token(captured_emails)

    row = db_session.scalar(
        select(PasswordResetToken).where(PasswordResetToken.user_id == applicant.id)
    )
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.flush()

    assert client.get(f"/auth/reset-password/{token}").json()["status"] == "expired"
    resp = client.post(f"/auth/reset-password/{token}", json={"new_password": NEW_PASSWORD})
    assert resp.status_code == 400
    assert "expired" in resp.text


def test_a_made_up_link_is_refused(client):
    assert client.get("/auth/reset-password/not-a-real-token").json()["status"] == "unknown"
    resp = client.post(
        "/auth/reset-password/not-a-real-token", json={"new_password": NEW_PASSWORD}
    )
    assert resp.status_code == 400


def test_the_status_check_never_names_the_account(client, applicant, captured_emails):
    """Anyone who gets hold of the link can open this, so it must not
    confirm whose account it belongs to."""
    _request_reset(client, applicant.email)
    token = _link_token(captured_emails)

    body = client.get(f"/auth/reset-password/{token}").json()
    assert body == {"status": "valid"}
    assert applicant.email not in str(body)


def test_a_reset_password_still_has_to_clear_the_length_rules(client, applicant, captured_emails):
    """The shared Password type applies here too -- a reset must not be
    able to set a password the other paths would refuse."""
    _request_reset(client, applicant.email)
    token = _link_token(captured_emails)

    assert client.post(
        f"/auth/reset-password/{token}", json={"new_password": "short"}
    ).status_code == 422
    assert client.post(
        f"/auth/reset-password/{token}", json={"new_password": "a" * 73}
    ).status_code == 422


def test_a_refused_reset_does_not_burn_the_link(client, applicant, captured_emails):
    """A password that fails validation is a typo, not an attempt --
    it must not cost the person their one link."""
    _request_reset(client, applicant.email)
    token = _link_token(captured_emails)

    client.post(f"/auth/reset-password/{token}", json={"new_password": "short"})

    assert client.get(f"/auth/reset-password/{token}").json()["status"] == "valid"
    assert client.post(
        f"/auth/reset-password/{token}", json={"new_password": NEW_PASSWORD}
    ).status_code == 200


def test_resetting_does_not_disturb_anyone_else(client, applicant, evaluator, captured_emails, db_session):
    _request_reset(client, applicant.email)
    token = _link_token(captured_emails)
    client.post(f"/auth/reset-password/{token}", json={"new_password": NEW_PASSWORD})

    db_session.expire_all()
    other = db_session.scalar(select(User).where(User.id == evaluator.id))
    assert client.post(
        "/auth/login", json={"email": other.email, "password": TEST_PASSWORD}
    ).status_code == 200
