"""Tests for two gaps found in an external review: brute-force
protection on login, and what happens when a session runs out mid-use.

Both were real. Login verified a dummy hash to defeat timing attacks but
had no limit on how many passwords could be tried; the access token
expired on a hard 60-minute timer with no renewal, so a long working
session simply began failing.
"""

import time

import jwt
import pytest

from app.infra import rate_limit
from app.infra.deps import RENEWED_TOKEN_HEADER
from app.infra.config import settings
from tests.conftest import TEST_PASSWORD, auth_headers


@pytest.fixture(autouse=True)
def _clean_attempt_counters():
    """The limiter is process-local by design, so one test's failures
    would otherwise lock out the next."""
    rate_limit.reset_all()
    yield
    rate_limit.reset_all()


def _login(client, email: str, password: str):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_repeated_bad_passwords_are_locked_out(client, hr_admin):
    email = "hr-test@arkivetesting.com"
    for _ in range(rate_limit.MAX_ATTEMPTS):
        assert _login(client, email, "wrong-password").status_code == 401

    resp = _login(client, email, "wrong-password")
    assert resp.status_code == 429, resp.text
    assert "Retry-After" in resp.headers
    assert "Too many failed sign-in attempts" in resp.json()["detail"]


def test_the_lockout_applies_even_to_the_correct_password(client, hr_admin):
    """Otherwise the limit would be trivially bypassable by an attacker
    who happens to guess right on the attempt after being blocked."""
    email = "hr-test@arkivetesting.com"
    for _ in range(rate_limit.MAX_ATTEMPTS):
        _login(client, email, "wrong-password")
    assert _login(client, email, TEST_PASSWORD).status_code == 429


def test_a_successful_login_clears_earlier_failures(client, hr_admin):
    """A few fat-fingered attempts followed by the right password must
    leave nothing behind — otherwise ordinary mistyping accumulates
    toward a lockout across an entire day."""
    email = "hr-test@arkivetesting.com"
    for _ in range(rate_limit.MAX_ATTEMPTS - 1):
        assert _login(client, email, "wrong-password").status_code == 401

    assert _login(client, email, TEST_PASSWORD).status_code == 200

    # The counter is back to zero, so a full run of failures is needed
    # again before any lockout.
    for _ in range(rate_limit.MAX_ATTEMPTS - 1):
        assert _login(client, email, "wrong-password").status_code == 401


def test_one_account_being_attacked_does_not_lock_out_another(client, hr_admin, evaluator):
    """The key includes the email, so an attacker hammering one account
    cannot deny service to everyone else from the same address."""
    for _ in range(rate_limit.MAX_ATTEMPTS + 1):
        _login(client, "hr-test@arkivetesting.com", "wrong-password")

    assert _login(client, "evaluator-test@arkivetesting.com", TEST_PASSWORD).status_code == 200


def test_a_fresh_token_is_not_renewed(client, hr_admin):
    """Renewing on every request would mint a token per API call for no
    benefit. Nothing should happen in the first half of a token's life."""
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    resp = client.get("/hr/applications", headers=headers)
    assert resp.status_code == 200
    assert RENEWED_TOKEN_HEADER not in resp.headers


def test_a_token_past_halfway_is_renewed_silently(client, hr_admin):
    """The point of the whole mechanism: someone still working never hits
    the expiry cliff, and the request itself succeeds as normal."""
    now = int(time.time())
    lifetime = settings.access_token_expire_minutes * 60
    # Issued far enough in the past to be past halfway, but not expired.
    stale = jwt.encode(
        {
            "user_id": hr_admin.id,
            "role": hr_admin.role.value,
            "iat": now - int(lifetime * 0.75),
            "exp": now + int(lifetime * 0.25),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    resp = client.get("/hr/applications", headers={"Authorization": f"Bearer {stale}"})
    assert resp.status_code == 200, resp.text

    renewed = resp.headers.get(RENEWED_TOKEN_HEADER)
    assert renewed, "expected a renewed token past the halfway point"

    # The replacement is a genuinely usable token for the same person,
    # with a later expiry than the one it replaced.
    payload = jwt.decode(renewed, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    assert payload["user_id"] == hr_admin.id
    assert payload["exp"] > now + int(lifetime * 0.25)
    assert client.get("/hr/applications", headers={"Authorization": f"Bearer {renewed}"}).status_code == 200


def test_an_expired_token_is_still_rejected(client, hr_admin):
    """Sliding expiry must not become no expiry: once a token is actually
    past its expiry it is refused, renewal or not."""
    now = int(time.time())
    expired = jwt.encode(
        {"user_id": hr_admin.id, "role": hr_admin.role.value, "iat": now - 7200, "exp": now - 60},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    resp = client.get("/hr/applications", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401
    assert RENEWED_TOKEN_HEADER not in resp.headers


# --- Signup volume limit -------------------------------------------------
#
# the mirror image of a brute-forced login: every request *succeeds*
# here, and it's the successes that have to be counted


def _signup(client, email: str, password: str = "signup-password-123"):
    return client.post(
        "/auth/signup",
        json={"email": email, "password": password, "full_name": "Scripted Account"},
    )


def test_scripted_account_creation_is_cut_off(client):
    for i in range(rate_limit.SIGNUP_MAX_ACCOUNTS):
        assert _signup(client, f"bulk-{i}@arkivetesting.com").status_code == 201

    resp = _signup(client, "bulk-over@arkivetesting.com")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    # The account past the limit must not exist — a 429 that still wrote
    # the row would be theatre.
    assert _login(client, "bulk-over@arkivetesting.com", "signup-password-123").status_code == 401


def test_a_successful_signup_does_not_reset_the_signup_budget(client):
    """Login clears its counter on success; signup must not, or a caller
    could refill their own budget simply by succeeding."""
    for i in range(rate_limit.SIGNUP_MAX_ACCOUNTS):
        assert _signup(client, f"nonreset-{i}@arkivetesting.com").status_code == 201

    assert _signup(client, f"nonreset-final@arkivetesting.com").status_code == 429


def test_a_rejected_signup_is_not_counted_against_the_limit(client, applicant):
    """A duplicate email is a 409 and never creates anything, so it must
    not consume the budget of the person who then signs up correctly."""
    taken = applicant.email
    for _ in range(rate_limit.SIGNUP_MAX_ACCOUNTS + 3):
        assert _signup(client, taken).status_code == 409

    assert _signup(client, "after-conflicts@arkivetesting.com").status_code == 201


def test_the_login_limit_and_the_signup_limit_are_separate_budgets(client, hr_admin):
    """They share one store; they must not share one bucket."""
    for _ in range(rate_limit.MAX_ATTEMPTS):
        assert _login(client, "hr-test@arkivetesting.com", "wrong-password").status_code == 401
    assert _login(client, "hr-test@arkivetesting.com", "wrong-password").status_code == 429

    # Locked out of login; still able to register.
    assert _signup(client, "unaffected@arkivetesting.com").status_code == 201
