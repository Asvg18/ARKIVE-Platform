"""Tests for changing one's own password and switching an account off.

`is_active` is honoured on every request, so switching it off through
the API (rather than by editing the database) is how a departed HR
admin's access is removed.
"""

from sqlalchemy import select

from app.infra import rate_limit
from app.models.enums import UserRole
from app.models.user import User
from tests.conftest import TEST_PASSWORD, auth_headers

NEW_PASSWORD = "a-brand-new-password"


def _headers(client, user: User):
    return auth_headers(client, user.email)


# --------------------------------------------------------------------
# Changing your own password
# --------------------------------------------------------------------


def test_changing_a_password_lets_the_new_one_sign_in_and_retires_the_old(client, applicant):
    resp = client.post(
        "/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD},
        headers=_headers(client, applicant),
    )
    assert resp.status_code == 204, resp.text

    with_new = client.post("/auth/login", json={"email": applicant.email, "password": NEW_PASSWORD})
    assert with_new.status_code == 200, with_new.text

    with_old = client.post("/auth/login", json={"email": applicant.email, "password": TEST_PASSWORD})
    assert with_old.status_code == 401


def test_every_role_can_change_its_own_password(client, hr_admin, evaluator, applicant):
    """No role carve-outs. An evaluator whose password was set months
    ago at invite time needs this as much as anyone."""
    for user in (hr_admin, evaluator, applicant):
        resp = client.post(
            "/auth/change-password",
            json={"current_password": TEST_PASSWORD, "new_password": f"new-{user.id}-password"},
            headers=_headers(client, user),
        )
        assert resp.status_code == 204, f"{user.role}: {resp.text}"


def test_the_wrong_current_password_is_refused(client, applicant):
    resp = client.post(
        "/auth/change-password",
        json={"current_password": "not-my-password", "new_password": NEW_PASSWORD},
        headers=_headers(client, applicant),
    )
    assert resp.status_code == 403, resp.text


def test_a_wrong_current_password_is_not_a_401(client, applicant):
    """The client treats any 401 as an expired session and signs the
    user out. A typo in a form field must not throw away the session the
    form is sitting in."""
    resp = client.post(
        "/auth/change-password",
        json={"current_password": "not-my-password", "new_password": NEW_PASSWORD},
        headers=_headers(client, applicant),
    )
    assert resp.status_code != 401


def test_a_failed_attempt_leaves_the_old_password_working(client, applicant):
    client.post(
        "/auth/change-password",
        json={"current_password": "not-my-password", "new_password": NEW_PASSWORD},
        headers=_headers(client, applicant),
    )
    still_works = client.post("/auth/login", json={"email": applicant.email, "password": TEST_PASSWORD})
    assert still_works.status_code == 200, still_works.text


def test_changing_a_password_requires_being_signed_in(client):
    resp = client.post(
        "/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 401


def test_the_new_password_must_differ_from_the_current_one(client, applicant):
    resp = client.post(
        "/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": TEST_PASSWORD},
        headers=_headers(client, applicant),
    )
    assert resp.status_code == 422, resp.text
    assert "different" in resp.text.lower()


def test_the_new_password_still_has_to_clear_the_length_rules(client, applicant):
    """The shared Password type applies here too -- a path that sets a
    password should not be able to set one the other paths would
    refuse."""
    too_short = client.post(
        "/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "short"},
        headers=_headers(client, applicant),
    )
    assert too_short.status_code == 422

    too_long = client.post(
        "/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "a" * 73},
        headers=_headers(client, applicant),
    )
    assert too_long.status_code == 422


def test_guessing_the_current_password_is_rate_limited(client, applicant):
    """The attacker here is at an unlocked laptop, so they are the
    legitimate address -- the limit is keyed on the account instead."""
    rate_limit.reset_all()
    headers = _headers(client, applicant)
    for _ in range(rate_limit.MAX_ATTEMPTS):
        client.post(
            "/auth/change-password",
            json={"current_password": "wrong", "new_password": NEW_PASSWORD},
            headers=headers,
        )

    locked = client.post(
        "/auth/change-password",
        json={"current_password": "wrong", "new_password": NEW_PASSWORD},
        headers=headers,
    )
    assert locked.status_code == 429, locked.text
    rate_limit.reset_all()


def test_a_successful_change_clears_the_earlier_failures(client, applicant):
    """A few fat-fingered attempts followed by the right password should
    leave nothing behind, same as login."""
    rate_limit.reset_all()
    headers = _headers(client, applicant)
    for _ in range(rate_limit.MAX_ATTEMPTS - 1):
        client.post(
            "/auth/change-password",
            json={"current_password": "wrong", "new_password": NEW_PASSWORD},
            headers=headers,
        )

    ok = client.post(
        "/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD},
        headers=headers,
    )
    assert ok.status_code == 204, ok.text
    assert rate_limit.seconds_until_retry(f"change-password|{applicant.id}") == 0
    rate_limit.reset_all()


# --------------------------------------------------------------------
# Deactivating and reactivating staff
# --------------------------------------------------------------------


def test_a_deactivated_evaluator_can_no_longer_sign_in(client, hr_admin, evaluator):
    resp = client.post(
        f"/hr/staff/{evaluator.id}/deactivate", headers=_headers(client, hr_admin)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False

    login = client.post("/auth/login", json={"email": evaluator.email, "password": TEST_PASSWORD})
    assert login.status_code == 401


def test_a_deactivated_account_loses_access_on_a_token_it_already_held(client, hr_admin, evaluator):
    """The point of reading the live row on every request rather than
    trusting the token: revoking access takes effect now, not whenever
    the token they are holding happens to expire."""
    evaluator_headers = _headers(client, evaluator)
    assert client.get("/auth/me", headers=evaluator_headers).status_code == 200

    client.post(f"/hr/staff/{evaluator.id}/deactivate", headers=_headers(client, hr_admin))

    assert client.get("/auth/me", headers=evaluator_headers).status_code == 401


def test_reactivating_restores_access_with_the_same_password(client, hr_admin, evaluator):
    admin_headers = _headers(client, hr_admin)
    client.post(f"/hr/staff/{evaluator.id}/deactivate", headers=admin_headers)

    resp = client.post(f"/hr/staff/{evaluator.id}/reactivate", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is True

    login = client.post("/auth/login", json={"email": evaluator.email, "password": TEST_PASSWORD})
    assert login.status_code == 200, login.text


def test_an_admin_cannot_deactivate_themselves(client, hr_admin):
    resp = client.post(f"/hr/staff/{hr_admin.id}/deactivate", headers=_headers(client, hr_admin))
    assert resp.status_code == 409, resp.text


def test_the_system_can_never_be_left_without_an_active_admin(client, hr_admin, make_user, db_session):
    """The property that actually matters, rather than the line of code
    that implements it.

    Losing the last administrator has no way back: inviting a
    replacement is itself an admin-only action, so the only repair would
    be editing the database. The self-check is what prevents it -- an
    actor is always an active admin, so the last active admin can only
    ever be their own target -- which is why no separate "last admin"
    count exists to test.

    Driven here by having two admins try every order they could remove
    each other in."""
    second_admin = make_user("second-admin@arkivetesting.com", UserRole.hr_admin, super_admin=True)
    db_session.flush()

    # Each one switches the other off, then tries to finish the job on
    # themselves -- the only route to zero.
    client.post(f"/hr/staff/{hr_admin.id}/deactivate", headers=_headers(client, second_admin))
    last_one = client.post(
        f"/hr/staff/{second_admin.id}/deactivate", headers=_headers(client, second_admin)
    )
    assert last_one.status_code == 409, last_one.text

    # The endpoints wrote through the same session, so drop the cached
    # attribute values before asking the database what is true.
    #
    # Scoped to the two accounts this test made, not a count of every
    # admin: these run against the real dev database, which carries
    # seeded rows, so a global count would be measuring the fixtures.
    db_session.expire_all()
    pair = db_session.scalars(
        select(User).where(User.id.in_([hr_admin.id, second_admin.id]))
    ).all()
    still_active = [u.id for u in pair if u.is_active]
    assert still_active == [second_admin.id]


def test_a_deactivated_admin_cannot_act_as_one(client, hr_admin, make_user, db_session):
    """Follows from reading the live row on every request, and is what
    makes the invariant above hold rather than merely look true: a
    switched-off admin cannot switch anyone back on, themselves
    included."""
    second_admin = make_user("third-admin@arkivetesting.com", UserRole.hr_admin, super_admin=True)
    db_session.flush()
    victim_headers = _headers(client, hr_admin)

    client.post(f"/hr/staff/{hr_admin.id}/deactivate", headers=_headers(client, second_admin))

    resp = client.post(f"/hr/staff/{hr_admin.id}/reactivate", headers=victim_headers)
    assert resp.status_code == 401


def test_an_evaluator_cannot_deactivate_anyone(client, evaluator, hr_admin):
    resp = client.post(
        f"/hr/staff/{hr_admin.id}/deactivate", headers=_headers(client, evaluator)
    )
    assert resp.status_code == 403


def test_an_applicant_account_is_not_reachable_through_the_staff_routes(client, hr_admin, applicant):
    """Scoped to staff on purpose. Cutting off a candidate mid-pipeline
    is a different decision, and withdrawing their application is the
    action that exists for it."""
    resp = client.post(
        f"/hr/staff/{applicant.id}/deactivate", headers=_headers(client, hr_admin)
    )
    assert resp.status_code == 404, resp.text


def test_the_staff_roster_reports_who_is_active(client, hr_admin, evaluator):
    admin_headers = _headers(client, hr_admin)
    client.post(f"/hr/staff/{evaluator.id}/deactivate", headers=admin_headers)

    roster = client.get("/hr/staff", headers=admin_headers)
    assert roster.status_code == 200, roster.text
    by_email = {row["email"]: row for row in roster.json()}
    assert by_email[evaluator.email]["is_active"] is False
    assert by_email[hr_admin.email]["is_active"] is True
