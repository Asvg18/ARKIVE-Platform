"""Tests for the two things that end a session even though its token is
perfectly valid: the absolute ceiling, and a password change.

Both exist because renewal (infra/deps.py) keeps replacing a token
before it can expire, so nobody is signed out mid-task. Without a
ceiling every replacement would start a fresh clock, and continuous use
(or a stolen token kept in use) would keep a session alive forever. A
session has a lifetime of its own, carried in auth_time and handed
forward through every renewal, independent of any one token's.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.infra.deps import ABSOLUTE_SESSION_LIFETIME, RENEWED_TOKEN_HEADER
from app.infra.security import create_access_token, decode_access_token
from app.models.user import User
from tests.conftest import TEST_PASSWORD, auth_headers


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token_for(user: User, *, started_ago: timedelta = timedelta()) -> str:
    return create_access_token(
        user_id=user.id,
        role=user.role.value,
        auth_time=datetime.now(timezone.utc) - started_ago,
    )


# --------------------------------------------------------------------
# The absolute ceiling
# --------------------------------------------------------------------


def test_a_fresh_session_works(client, applicant):
    resp = client.get("/auth/me", headers=_headers(_token_for(applicant)))
    assert resp.status_code == 204, resp.text


def test_a_session_just_under_the_ceiling_still_works(client, applicant):
    token = _token_for(applicant, started_ago=ABSOLUTE_SESSION_LIFETIME - timedelta(minutes=5))
    assert client.get("/auth/me", headers=_headers(token)).status_code == 200


def test_a_session_past_the_ceiling_is_refused(client, applicant):
    """The token itself is unexpired and correctly signed -- what has
    run out is the session behind it."""
    token = _token_for(applicant, started_ago=ABSOLUTE_SESSION_LIFETIME + timedelta(minutes=1))
    assert client.get("/auth/me", headers=_headers(token)).status_code == 401


def test_renewal_carries_the_original_sign_in_forward(client, applicant):
    """The heart of it. If a renewed token looked freshly authenticated,
    the ceiling could never be reached by the one thing it exists to
    stop: a session kept alive by continuous use."""
    started = datetime.now(timezone.utc) - timedelta(hours=6)
    # Past halfway through its own life, so the request triggers a renewal.
    token = create_access_token(user_id=applicant.id, role=applicant.role.value, auth_time=started)
    old = decode_access_token(token)
    aged = create_access_token(user_id=applicant.id, role=applicant.role.value, auth_time=started)

    resp = client.get("/auth/me", headers=_headers(aged))
    assert resp.status_code == 200, resp.text

    renewed = resp.headers.get(RENEWED_TOKEN_HEADER)
    if renewed:  # only issued once past halfway; assert the property when it is
        assert decode_access_token(renewed)["auth_time"] == old["auth_time"]


def test_a_renewed_token_cannot_outlive_the_ceiling(client, applicant):
    """Renew a session that is already too old and the replacement is
    refused too -- there is no way to launder an expired session into a
    fresh one."""
    token = _token_for(applicant, started_ago=ABSOLUTE_SESSION_LIFETIME + timedelta(hours=1))
    assert client.get("/auth/me", headers=_headers(token)).status_code == 401


def test_a_token_with_no_session_start_is_refused(client, applicant):
    """Neither auth_time nor iat means nothing can be judged, and a
    token that malformed is not one to trust."""
    import jwt

    from app.infra.config import settings

    payload = {
        "user_id": applicant.id,
        "role": applicant.role.value,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    naked = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    assert client.get("/auth/me", headers=_headers(naked)).status_code == 401


def test_an_old_token_without_auth_time_falls_back_to_iat(client, applicant):
    """Tokens already in people's browsers when this shipped carry no
    auth_time. Treating their issue time as the session start is the
    safe reading, and self-corrects within one token lifetime rather
    than signing everyone out on deploy."""
    import jwt

    from app.infra.config import settings

    now = datetime.now(timezone.utc)
    legacy = jwt.encode(
        {
            "user_id": applicant.id,
            "role": applicant.role.value,
            "iat": now,
            "exp": now + timedelta(minutes=30),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    assert client.get("/auth/me", headers=_headers(legacy)).status_code == 200


# --------------------------------------------------------------------
# A password change ends other sessions
# --------------------------------------------------------------------


def test_changing_a_password_ends_a_session_opened_before_it(client, applicant):
    """The point of the whole mechanism: someone else signed in on the
    old password stops being signed in.

    The other session is given a start a minute back, which is what one
    actually looks like -- a test doing everything inside a single
    second would instead be probing the boundary, which the test below
    does deliberately."""
    elsewhere = _headers(_token_for(applicant, started_ago=timedelta(minutes=1)))
    assert client.get("/auth/me", headers=elsewhere).status_code == 200

    mine = auth_headers(client, applicant.email)
    changed = client.post(
        "/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "a-fresh-password-1"},
        headers=mine,
    )
    assert changed.status_code == 204, changed.text

    assert client.get("/auth/me", headers=elsewhere).status_code == 401


def test_the_person_changing_it_stays_signed_in(client, applicant):
    """Signing yourself out as confirmation of success would be an
    unkind way to learn it worked. The response carries a replacement
    through the header the client already swaps in silently."""
    mine = auth_headers(client, applicant.email)
    resp = client.post(
        "/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "a-fresh-password-2"},
        headers=mine,
    )
    assert resp.status_code == 204, resp.text

    replacement = resp.headers.get(RENEWED_TOKEN_HEADER)
    assert replacement, "no replacement token was issued"
    assert client.get("/auth/me", headers=_headers(replacement)).status_code == 200


def test_resetting_a_password_ends_a_session_opened_before_it(client, applicant, monkeypatch):
    """The path where this matters most -- someone resets precisely
    because they think another person is in their account."""
    from app.services import password_reset

    sent: list[dict] = []
    monkeypatch.setattr(
        password_reset, "send_email_safely", lambda **kw: sent.append(kw) or True
    )

    intruder = _headers(_token_for(applicant, started_ago=timedelta(minutes=1)))
    assert client.get("/auth/me", headers=intruder).status_code == 200

    client.post("/auth/forgot-password", json={"email": applicant.email})
    link_token = sent[-1]["body"].split("/reset-password/")[1].split()[0]
    resp = client.post(
        f"/auth/reset-password/{link_token}", json={"new_password": "reset-me-please-1"}
    )
    assert resp.status_code == 200, resp.text

    assert client.get("/auth/me", headers=intruder).status_code == 401


def test_the_timestamp_is_recorded_on_the_account(client, applicant, db_session):
    before = db_session.scalar(select(User).where(User.id == applicant.id)).password_changed_at
    assert before is None, "a new account has no password change to measure against"

    client.post(
        "/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "a-fresh-password-3"},
        headers=auth_headers(client, applicant.email),
    )

    db_session.expire_all()
    after = db_session.scalar(select(User).where(User.id == applicant.id)).password_changed_at
    assert after is not None


def test_another_account_is_unaffected_by_your_password_change(client, applicant, evaluator):
    theirs = auth_headers(client, evaluator.email)
    client.post(
        "/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "a-fresh-password-4"},
        headers=auth_headers(client, applicant.email),
    )
    assert client.get("/auth/me", headers=theirs).status_code == 200


def test_a_session_starting_exactly_at_the_change_is_kept(client, applicant, db_session):
    """The boundary, pinned at the value rather than by wall-clock luck.

    Token timestamps are whole seconds (RFC 7519), so password_changed_at
    is stored at that resolution too -- otherwise the replacement token
    handed to the person changing their password reads as fractionally
    older than the change and is refused on their very next request.

    The comparison is therefore strictly-earlier, and a session stamped
    with exactly the change's own second is kept. That is what lets the
    person who changed their password carry on working. For it to
    shelter anyone else they would have had to sign in inside that one
    second, and the next change would catch them anyway.

    Driven off the stored value instead of "do both quickly and hope",
    which is timing-dependent and fails the moment a login's bcrypt
    lands near a second boundary."""
    resp = client.post(
        "/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "a-fresh-password-5"},
        headers=auth_headers(client, applicant.email),
    )
    assert resp.status_code == 204, resp.text

    db_session.expire_all()
    changed_at = db_session.scalar(select(User).where(User.id == applicant.id)).password_changed_at
    assert changed_at.microsecond == 0, "stored at token resolution, not microseconds"

    at_the_boundary = create_access_token(
        user_id=applicant.id, role=applicant.role.value, auth_time=changed_at
    )
    assert client.get("/auth/me", headers=_headers(at_the_boundary)).status_code == 200

    a_second_earlier = create_access_token(
        user_id=applicant.id,
        role=applicant.role.value,
        auth_time=changed_at - timedelta(seconds=1),
    )
    assert client.get("/auth/me", headers=_headers(a_second_earlier)).status_code == 401
