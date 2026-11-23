"""Tests for /auth/* — login, signup, and /auth/me. Prior coverage was
incidental only (the shared auth_headers helper exercises the happy-path
login implicitly); this is the first real coverage of the auth router
itself, including applicant self-registration (POST /auth/signup)."""

from tests.conftest import TEST_PASSWORD


def test_signup_creates_a_working_applicant_account(client):
    resp = client.post(
        "/auth/signup",
        json={"email": "new-applicant@arkivetesting.com", "password": "a-real-password", "full_name": "Nia Newcomer"},
    )

    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    assert me.json()["role"] == "applicant"
    assert me.json()["full_name"] == "Nia Newcomer"
    assert me.json()["email"] == "new-applicant@arkivetesting.com"


def test_signup_duplicate_email_rejected(client):
    body = {"email": "dupe@arkivetesting.com", "password": "a-real-password", "full_name": "First Try"}
    first = client.post("/auth/signup", json=body)
    assert first.status_code == 201, first.text

    second = client.post(
        "/auth/signup",
        json={"email": "dupe@arkivetesting.com", "password": "another-password", "full_name": "Second Try"},
    )
    assert second.status_code == 409


def test_signup_password_too_short_rejected(client):
    resp = client.post(
        "/auth/signup",
        json={"email": "short-pw@arkivetesting.com", "password": "short", "full_name": "Short Password"},
    )
    assert resp.status_code == 422


def test_signup_password_at_the_bcrypt_limit_is_accepted(client):
    """72 bytes is the largest bcrypt takes, so it has to be allowed --
    a cap that is off by one would reject a legitimate password."""
    resp = client.post(
        "/auth/signup",
        json={
            "email": "at-limit@arkivetesting.com",
            "password": "a" * 72,
            "full_name": "Exactly Seventy Two",
        },
    )
    assert resp.status_code == 201, resp.text


def test_signup_password_past_the_bcrypt_limit_is_a_validation_error_not_a_crash(client):
    """bcrypt raises above 72 bytes rather than truncating, and nothing
    capped the length -- so a password-manager passphrase reached the
    hasher and came back a 500. The person who is most careful about
    their password was the one getting an error page."""
    resp = client.post(
        "/auth/signup",
        json={
            "email": "too-long@arkivetesting.com",
            "password": "a" * 73,
            "full_name": "One Byte Too Far",
        },
    )
    assert resp.status_code == 422, resp.text
    assert "too long" in resp.text.lower()


def test_a_multibyte_password_is_measured_in_bytes_not_characters(client):
    """The limit bcrypt enforces is 72 *bytes*. "ñ" is one character and
    two bytes, so 40 of them is 80 bytes -- under any character-based cap
    and still over the real one."""
    resp = client.post(
        "/auth/signup",
        json={
            "email": "multibyte@arkivetesting.com",
            "password": "ñ" * 40,
            "full_name": "Forty Characters Eighty Bytes",
        },
    )
    assert resp.status_code == 422, resp.text


def test_login_with_an_over_long_password_is_rejected_not_a_crash(client, applicant):
    """Login deliberately does not cap the password it is handed: a wrong
    password answers 401 whatever its length, so the response never
    varies with what was typed. Before this it raised instead."""
    resp = client.post(
        "/auth/login", json={"email": applicant.email, "password": "a" * 200}
    )
    assert resp.status_code == 401, resp.text


def test_signup_then_login_with_the_chosen_password(client):
    signup = client.post(
        "/auth/signup",
        json={"email": "roundtrip@arkivetesting.com", "password": "my-own-password", "full_name": "Round Tripper"},
    )
    assert signup.status_code == 201, signup.text

    login = client.post(
        "/auth/login", json={"email": "roundtrip@arkivetesting.com", "password": "my-own-password"}
    )
    assert login.status_code == 200, login.text
    assert login.json()["access_token"]


def test_login_wrong_password_rejected(client, applicant):
    resp = client.post("/auth/login", json={"email": applicant.email, "password": "definitely-not-it"})
    assert resp.status_code == 401


def test_login_nonexistent_email_rejected(client):
    resp = client.post("/auth/login", json={"email": "nobody@arkivetesting.com", "password": "whatever"})
    assert resp.status_code == 401


def test_login_correct_credentials_reach_me(client, applicant):
    login = client.post("/auth/login", json={"email": applicant.email, "password": TEST_PASSWORD})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    assert me.json()["id"] == applicant.id


def test_me_without_token_rejected(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_a_password_everybody_picks_is_refused(client):
    """Eight characters is the only length rule, so "password123" and
    "12345678" both cleared it -- which are the first two things an
    online guessing attack tries."""
    resp = client.post(
        "/auth/signup",
        json={
            "email": "common-pw@arkivetesting.com",
            "password": "password123",
            "full_name": "Common Password",
        },
    )
    assert resp.status_code == 422, resp.text
    assert "commonly used" in resp.text.lower()


def test_capitalising_a_common_password_does_not_get_it_past(client):
    """"Password123" is no harder to guess than "password123", and
    someone refused the one would otherwise just shift-key the other."""
    resp = client.post(
        "/auth/signup",
        json={
            "email": "shifted-pw@arkivetesting.com",
            "password": "Password123",
            "full_name": "Shifted Password",
        },
    )
    assert resp.status_code == 422, resp.text


def test_an_ordinary_password_is_not_caught_by_the_common_list(client):
    """The refusal list must not become a complexity policy by accident
    -- a perfectly ordinary chosen password still works."""
    resp = client.post(
        "/auth/signup",
        json={
            "email": "ordinary-pw@arkivetesting.com",
            "password": "kettle-orbit-marmalade",
            "full_name": "Ordinary Password",
        },
    )
    assert resp.status_code == 201, resp.text
