"""Super admin (28 Sep 2026): account management -- inviting staff,
switching accounts off and on, granting super admin -- belongs to super
admins only. Every other HR admin keeps every hiring page.
"""

from sqlalchemy import select

from app.models.enums import UserRole
from app.models.user import User
from tests.conftest import TEST_PASSWORD, auth_headers


def _headers(client, user):
    return auth_headers(client, user.email)


def test_a_plain_hr_admin_is_refused_every_account_route(client, plain_hr_admin, evaluator):
    """The sidebar hiding User Management is a courtesy; this is the
    boundary. Every route, not a sample, because one forgotten route is
    the whole hole."""
    headers = _headers(client, plain_hr_admin)
    routes = [
        ("get", "/hr/staff", None),
        ("get", "/hr/invites", None),
        ("post", "/hr/invites", {"email": "someone@arkivetesting.com", "role": "evaluator"}),
        ("post", "/hr/invites/1/revoke", None),
        ("get", "/hr/invitation-email", None),
        ("post", "/hr/invites/1/resend", None),
        ("get", f"/hr/staff/{evaluator.id}/waiting-interviews", None),
        ("post", f"/hr/staff/{evaluator.id}/deactivate", None),
        ("post", f"/hr/staff/{evaluator.id}/reactivate", None),
        ("post", f"/hr/staff/{plain_hr_admin.id}/grant-super-admin", None),
        ("post", f"/hr/staff/{plain_hr_admin.id}/remove-super-admin", None),
    ]
    for method, path, body in routes:
        resp = getattr(client, method)(path, headers=headers, **({"json": body} if body else {}))
        assert resp.status_code == 403, f"{method.upper()} {path} -> {resp.status_code}"
        assert resp.json()["detail"] == "Only a super admin can manage accounts."


def test_a_plain_hr_admin_keeps_the_hiring_pages(client, plain_hr_admin):
    headers = _headers(client, plain_hr_admin)
    assert client.get("/hr/dashboard/summary", headers=headers).status_code == 200
    assert client.get("/hr/applications", headers=headers).status_code == 200
    assert client.get("/hr/evaluators", headers=headers).status_code == 200


def test_the_signed_in_account_says_whether_it_is_a_super_admin(client, hr_admin, plain_hr_admin):
    """What the HR portal reads to decide whether to show User Management."""
    assert client.get("/auth/me", headers=_headers(client, hr_admin)).json()["is_super_admin"] is True
    assert client.get("/auth/me", headers=_headers(client, plain_hr_admin)).json()["is_super_admin"] is False


def test_granting_super_admin_opens_user_management(client, hr_admin, plain_hr_admin):
    plain_headers = _headers(client, plain_hr_admin)
    assert client.get("/hr/staff", headers=plain_headers).status_code == 403

    resp = client.post(
        f"/hr/staff/{plain_hr_admin.id}/grant-super-admin", headers=_headers(client, hr_admin)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_super_admin"] is True

    # the same session, no sign-in again: the live row is what is checked
    assert client.get("/hr/staff", headers=plain_headers).status_code == 200


def test_removing_super_admin_takes_effect_on_the_next_request(client, hr_admin, make_user):
    second = make_user("second-super@arkivetesting.com", UserRole.hr_admin, super_admin=True)
    second_headers = _headers(client, second)
    assert client.get("/hr/staff", headers=second_headers).status_code == 200

    resp = client.post(f"/hr/staff/{second.id}/remove-super-admin", headers=_headers(client, hr_admin))
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_super_admin"] is False

    assert client.get("/hr/staff", headers=second_headers).status_code == 403
    # still an HR admin, with the hiring pages
    assert client.get("/hr/applications", headers=second_headers).status_code == 200


def test_nobody_can_remove_their_own_super_admin(client, hr_admin):
    resp = client.post(f"/hr/staff/{hr_admin.id}/remove-super-admin", headers=_headers(client, hr_admin))
    assert resp.status_code == 409, resp.text


def test_the_organization_always_keeps_a_super_admin(client, hr_admin, make_user, db_session):
    """Two super admins try every order they could strip each other in.
    As with deactivation, refusing it for yourself is the entire guard:
    the actor is always an active super admin."""
    second = make_user("other-super@arkivetesting.com", UserRole.hr_admin, super_admin=True)

    client.post(f"/hr/staff/{hr_admin.id}/remove-super-admin", headers=_headers(client, second))
    last = client.post(f"/hr/staff/{second.id}/remove-super-admin", headers=_headers(client, second))
    assert last.status_code == 409, last.text
    # the one who lost it can no longer act as a super admin at all
    comeback = client.post(
        f"/hr/staff/{second.id}/remove-super-admin", headers=_headers(client, hr_admin)
    )
    assert comeback.status_code == 403

    db_session.expire_all()
    pair = db_session.scalars(select(User).where(User.id.in_([hr_admin.id, second.id]))).all()
    assert [u.id for u in pair if u.is_super_admin] == [second.id]


def test_only_an_hr_admin_can_be_made_a_super_admin(client, hr_admin, evaluator):
    resp = client.post(f"/hr/staff/{evaluator.id}/grant-super-admin", headers=_headers(client, hr_admin))
    assert resp.status_code == 422, resp.text


def test_a_switched_off_account_cannot_be_made_a_super_admin(client, hr_admin, plain_hr_admin):
    admin_headers = _headers(client, hr_admin)
    client.post(f"/hr/staff/{plain_hr_admin.id}/deactivate", headers=admin_headers)

    resp = client.post(f"/hr/staff/{plain_hr_admin.id}/grant-super-admin", headers=admin_headers)
    assert resp.status_code == 409, resp.text


def test_a_super_admin_invitation_creates_a_super_admin(client, hr_admin):
    admin_headers = _headers(client, hr_admin)
    created = client.post(
        "/hr/invites",
        json={"email": "next-head@arkivetesting.com", "role": "hr_admin", "super_admin": True},
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["super_admin"] is True
    token = created.json()["token"]
    assert client.get(f"/invites/{token}").json()["super_admin"] is True

    accepted = client.post(f"/invites/{token}/accept", json={"full_name": "Next Head", "password": TEST_PASSWORD})
    assert accepted.status_code == 201, accepted.text
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {accepted.json()['access_token']}"})
    assert me.json()["role"] == "hr_admin"
    assert me.json()["is_super_admin"] is True


def test_an_ordinary_hr_invitation_creates_a_plain_hr_admin(client, hr_admin):
    created = client.post(
        "/hr/invites",
        json={"email": "hr-staff@arkivetesting.com", "role": "hr_admin"},
        headers=_headers(client, hr_admin),
    )
    token = created.json()["token"]
    accepted = client.post(f"/invites/{token}/accept", json={"full_name": "HR Staff", "password": TEST_PASSWORD})
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {accepted.json()['access_token']}"})
    assert me.json()["is_super_admin"] is False


def test_an_evaluator_cannot_be_invited_as_a_super_admin(client, hr_admin):
    resp = client.post(
        "/hr/invites",
        json={"email": "panel@arkivetesting.com", "role": "evaluator", "super_admin": True},
        headers=_headers(client, hr_admin),
    )
    assert resp.status_code == 422, resp.text


def test_the_roster_shows_who_is_a_super_admin(client, hr_admin, plain_hr_admin):
    roster = client.get("/hr/staff", headers=_headers(client, hr_admin)).json()
    by_email = {row["email"]: row for row in roster}
    assert by_email[hr_admin.email]["is_super_admin"] is True
    assert by_email[plain_hr_admin.email]["is_super_admin"] is False
