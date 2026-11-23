"""Black-box tests for the invite-link staff provisioning flow -- how
new hr_admin/evaluator accounts get created, replacing the old
temp-password flow.
"""

from datetime import datetime, timedelta, timezone

from app.models.invite import Invite
from tests.conftest import TEST_PASSWORD, auth_headers


def _invite_hr(client, headers, email="new-hire@arkivetesting.com", role="evaluator"):
    return client.post("/hr/invites", json={"email": email, "role": role}, headers=headers)


def test_create_invite(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = _invite_hr(client, headers)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["token"]
    assert body["email"] == "new-hire@arkivetesting.com"
    assert body["role"] == "evaluator"
    assert body["status"] == "pending"
    assert body["invited_by_name"] == hr_admin.full_name


def test_reinviting_pending_email_regenerates_instead_of_duplicating(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    first = _invite_hr(client, headers)
    second = _invite_hr(client, headers, role="hr_admin")

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["token"] != second.json()["token"]

    listing = client.get("/hr/invites", headers=headers)
    matching = [i for i in listing.json() if i["email"] == "new-hire@arkivetesting.com"]
    assert len(matching) == 1
    assert matching[0]["role"] == "hr_admin"


def test_create_invite_for_existing_user_email_rejected(client, hr_admin, evaluator):
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = _invite_hr(client, headers, email=evaluator.email)

    assert resp.status_code == 409


def test_non_hr_admin_cannot_create_invite(client, evaluator):
    headers = auth_headers(client, "evaluator-test@arkivetesting.com")

    resp = _invite_hr(client, headers)

    assert resp.status_code == 403


def test_staff_can_be_invited_with_any_valid_email(client, hr_admin):
    """No email domain is asked of staff (decided 1 Oct 2026): a personal
    address does as well as an organization one, for every kind of access."""
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    for email, access in [
        ("guest.panelist@gmail.com", {"role": "evaluator"}),
        ("new.hr@yahoo.com", {"role": "hr_admin"}),
        ("head.of.hr+testing@outlook.com", {"role": "hr_admin", "super_admin": True}),
    ]:
        resp = client.post("/hr/invites", json={"email": email, **access}, headers=headers)
        assert resp.status_code == 201, resp.text


def test_an_invite_still_needs_a_valid_email(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    for not_an_email in ["devon.cruz", "devon.cruz@", "@gmail.com", "devon cruz@gmail.com"]:
        resp = _invite_hr(client, headers, email=not_an_email)
        assert resp.status_code == 422, f"{not_an_email!r} -> {resp.status_code}"


def test_get_invite_status_for_pending_token(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    token = _invite_hr(client, headers).json()["token"]

    resp = client.get(f"/invites/{token}")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "email": "new-hire@arkivetesting.com",
        "role": "evaluator",
        "status": "pending",
        "super_admin": False,
    }


def test_get_invite_status_for_unknown_token(client, hr_admin):
    resp = client.get("/invites/not-a-real-token")

    assert resp.status_code == 404


def test_accept_invite_creates_account_with_invited_role(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    token = _invite_hr(client, headers, email="accepted@arkivetesting.com", role="hr_admin").json()["token"]

    resp = client.post(
        f"/invites/{token}/accept",
        json={"full_name": "Newly Accepted", "password": TEST_PASSWORD},
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["access_token"]

    login = client.post("/auth/login", json={"email": "accepted@arkivetesting.com", "password": TEST_PASSWORD})
    assert login.status_code == 200, login.text

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert me.json()["role"] == "hr_admin"


def test_accept_invite_with_an_over_long_password_is_a_validation_error_not_a_crash(client, hr_admin):
    """Same 72-byte bcrypt ceiling as self-registration. This is the path
    most likely to hit it -- an invited HR admin is the person most
    likely to be using a password manager."""
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    token = _invite_hr(client, headers, email="long-pw-invite@arkivetesting.com").json()["token"]

    resp = client.post(
        f"/invites/{token}/accept",
        json={"full_name": "Long Password", "password": "a" * 73},
    )

    assert resp.status_code == 422, resp.text
    assert "too long" in resp.text.lower()


def test_accept_invite_twice_fails(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    token = _invite_hr(client, headers, email="once-only@arkivetesting.com").json()["token"]

    first = client.post(f"/invites/{token}/accept", json={"full_name": "First", "password": TEST_PASSWORD})
    second = client.post(f"/invites/{token}/accept", json={"full_name": "Second", "password": TEST_PASSWORD})

    assert first.status_code == 201, first.text
    assert second.status_code == 409


def test_accept_expired_invite_fails(client, hr_admin, db_session):
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    token = _invite_hr(client, headers, email="really-expired@arkivetesting.com").json()["token"]

    invite = db_session.query(Invite).filter(Invite.email == "really-expired@arkivetesting.com").one()
    invite.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.flush()

    resp = client.post(f"/invites/{token}/accept", json={"full_name": "Too Late", "password": TEST_PASSWORD})

    assert resp.status_code == 409


def test_revoke_pending_invite_then_accept_fails(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    created = _invite_hr(client, headers, email="revoked@arkivetesting.com").json()
    token = created["token"]

    revoke = client.post(f"/hr/invites/{created['id']}/revoke", headers=headers)
    assert revoke.status_code == 200, revoke.text
    assert revoke.json()["status"] == "revoked"

    accept = client.post(f"/invites/{token}/accept", json={"full_name": "Nope", "password": TEST_PASSWORD})
    assert accept.status_code == 409


def test_revoke_already_accepted_invite_rejected(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    created = _invite_hr(client, headers, email="already-in@arkivetesting.com").json()
    client.post(f"/invites/{created['token']}/accept", json={"full_name": "In", "password": TEST_PASSWORD})

    resp = client.post(f"/hr/invites/{created['id']}/revoke", headers=headers)

    assert resp.status_code == 409


def test_list_staff_includes_hr_admin_and_evaluator(client, hr_admin, evaluator):
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.get("/hr/staff", headers=headers)

    assert resp.status_code == 200, resp.text
    emails = {row["email"] for row in resp.json()}
    assert hr_admin.email in emails
    assert evaluator.email in emails


def test_non_hr_admin_cannot_list_staff(client, evaluator):
    headers = auth_headers(client, "evaluator-test@arkivetesting.com")

    resp = client.get("/hr/staff", headers=headers)

    assert resp.status_code == 403


def test_an_invite_is_emailed_with_a_working_link(client, hr_admin, monkeypatch):
    """The invite goes out through the same mail machinery as password
    resets, so HR need not copy the link out and send it by hand.

    The sending moved to services/staff_accounts (28 Sep 2026), shared
    with the first-admin setup step, so that is where it is caught."""
    from app.services import staff_accounts

    sent: list[dict] = []
    monkeypatch.setattr(
        staff_accounts, "send_email_safely", lambda **kw: sent.append(kw) or True
    )

    headers = auth_headers(client, "hr-test@arkivetesting.com")
    resp = _invite_hr(client, headers, email="mailed@arkivetesting.com", role="evaluator")
    assert resp.status_code == 201, resp.text
    assert resp.json()["emailed"] is True

    assert len(sent) == 1
    assert sent[0]["to"] == "mailed@arkivetesting.com"

    # the link in the email is the one that actually works
    token = sent[0]["body"].split("/accept-invite/")[1].split()[0]
    assert client.get(f"/invites/{token}").json()["status"] == "pending"


def test_an_invite_still_works_when_mail_is_not_configured(client, hr_admin, monkeypatch):
    """SMTP is unset by default, and must never be the reason an invite
    cannot be created -- the link in the response is still usable by
    hand."""
    from app.services import staff_accounts

    monkeypatch.setattr(staff_accounts, "send_email_safely", lambda **kw: False)

    headers = auth_headers(client, "hr-test@arkivetesting.com")
    resp = _invite_hr(client, headers, email="unmailed@arkivetesting.com")

    assert resp.status_code == 201, resp.text
    assert resp.json()["emailed"] is False
    assert resp.json()["token"], "the link must still come back for HR to send"


def test_a_mail_server_that_explodes_does_not_lose_the_invite(client, hr_admin, monkeypatch):
    """The coupling this prevents -- HR invites someone, the relay is
    down, the request 500s and no invite exists -- looks harmless until
    it happens.

    Patches the *real* sender underneath rather than send_email_safely
    itself: replacing the function whose entire job is to swallow
    failures would be asserting the test's own stub, not the contract.
    """
    from app.services import email as email_service

    def _explode(**_kw):
        raise RuntimeError("relay refused the connection")

    monkeypatch.setattr(email_service, "send_email", _explode)

    headers = auth_headers(client, "hr-test@arkivetesting.com")
    resp = _invite_hr(client, headers, email="exploded@arkivetesting.com")

    assert resp.status_code == 201, resp.text
    assert resp.json()["emailed"] is False
    assert resp.json()["token"], "the link must still come back for HR to send"
