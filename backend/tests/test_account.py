"""Account Settings -- a person's own name, photo, staff details and
sign-in email (api/account.py, services/email_change.py)."""

import re
from datetime import datetime, timedelta, timezone

import pytest

from app.api import account as account_router
from app.models.email_change import EmailChangeToken
from app.models.enums import UserRole
from app.services import email_change
from tests.conftest import TEST_PASSWORD, auth_headers

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def test_me_reports_the_new_profile_fields(client, evaluator):
    headers = auth_headers(client, evaluator.email)

    me = client.get("/auth/me", headers=headers).json()

    assert me["avatar_url"] is None
    assert me["job_title"] is None
    assert me["pending_email"] is None
    assert "avatar_file" not in me


def test_me_reports_when_the_account_began_and_its_password_last_changed(client, evaluator):
    """The banner's "Member since" and the Password card's "Last changed"."""
    from tests.conftest import TEST_PASSWORD

    headers = auth_headers(client, evaluator.email)
    me = client.get("/auth/me", headers=headers).json()
    assert me["created_at"] is not None
    assert me["password_changed_at"] is None, "a new account has never changed its password"

    changed = client.post(
        "/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "a-fresh-password-9"},
        headers=headers,
    )
    replacement = {"Authorization": f"Bearer {changed.headers['X-Renewed-Token']}"}
    assert client.get("/auth/me", headers=replacement).json()["password_changed_at"] is not None


def test_staff_can_set_name_title_and_department(client, evaluator):
    headers = auth_headers(client, evaluator.email)

    resp = client.patch(
        "/account/profile",
        headers=headers,
        json={"full_name": "  Armando Bautista ", "job_title": "Dean", "department": "College of Computing"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert (body["full_name"], body["job_title"], body["department"]) == (
        "Armando Bautista",
        "Dean",
        "College of Computing",
    )
    # clearing a field means "not set", not a blank string
    cleared = client.patch("/account/profile", headers=headers, json={"department": "   "}).json()
    assert cleared["department"] is None
    assert cleared["job_title"] == "Dean"


def test_an_applicant_cannot_set_staff_fields_or_an_empty_name(client, applicant):
    headers = auth_headers(client, applicant.email)

    staff = client.patch("/account/profile", headers=headers, json={"job_title": "Dean"})
    empty = client.patch("/account/profile", headers=headers, json={"full_name": "  "})
    renamed = client.patch("/account/profile", headers=headers, json={"full_name": "Maria Santos"})

    assert staff.status_code == 403
    assert empty.status_code == 422
    assert renamed.json()["full_name"] == "Maria Santos"


def test_a_photo_is_stored_served_replaced_and_removed(client, evaluator, avatar_uploads):
    headers = auth_headers(client, evaluator.email)

    first = client.put("/account/avatar", headers=headers, files={"file": ("me.png", PNG, "image/png")})
    assert first.status_code == 200
    first_url = first.json()["avatar_url"]
    assert re.fullmatch(r"/avatars/[0-9a-f]{32}\.png", first_url)

    # served without a sign-in -- an <img> can't send one
    served = client.get(first_url)
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert served.content == PNG

    second = client.put("/account/avatar", headers=headers, files={"file": ("me.jpg", JPEG, "image/jpeg")})
    second_url = second.json()["avatar_url"]
    assert second_url != first_url and second_url.endswith(".jpg")
    assert client.get(first_url).status_code == 404, "the replaced photo should be deleted"
    assert len(list(avatar_uploads.iterdir())) == 1

    removed = client.delete("/account/avatar", headers=headers)
    assert removed.json()["avatar_url"] is None
    assert list(avatar_uploads.iterdir()) == []


def test_a_photo_is_judged_by_its_bytes_not_its_name(client, evaluator):
    headers = auth_headers(client, evaluator.email)

    svg = client.put(
        "/account/avatar",
        headers=headers,
        files={"file": ("me.png", b"<svg xmlns='http://www.w3.org/2000/svg'><script/></svg>", "image/png")},
    )
    huge = client.put(
        "/account/avatar",
        headers=headers,
        files={"file": ("me.png", PNG + b"\x00" * (2 * 1024 * 1024), "image/png")},
    )

    assert svg.status_code == 422
    assert huge.status_code == 413


def test_avatar_route_refuses_anything_but_a_photo_name(client):
    assert client.get("/avatars/..%2F..%2Fapp%2Fmain.py").status_code == 404
    assert client.get("/avatars/" + "a" * 32 + ".jpg").status_code == 404


def test_the_photo_travels_with_the_name(client, db_session, hr_admin, evaluator):
    evaluator.avatar_file = "b" * 32 + ".png"
    evaluator.job_title = "Dean"
    db_session.flush()
    headers = auth_headers(client, hr_admin.email)

    staff = {s["email"]: s for s in client.get("/hr/staff", headers=headers).json()}

    assert staff[evaluator.email]["avatar_url"] == "/avatars/" + "b" * 32 + ".png"
    assert staff[evaluator.email]["job_title"] == "Dean"


@pytest.fixture()
def sent_mail(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(email_change, "send_email_safely", lambda **kw: sent.append(kw) or True)
    return sent


def _link_token(mail: dict) -> str:
    return re.search(r"/confirm-email/(\S+)", mail["body"]).group(1)


def test_changing_email_waits_for_the_link_from_the_new_mailbox(client, db_session, evaluator, sent_mail):
    headers = auth_headers(client, evaluator.email)
    old_email = evaluator.email

    asked = client.post(
        "/account/email-change",
        headers=headers,
        json={"new_email": "armando.new@arkivetesting.com", "current_password": TEST_PASSWORD},
    )

    assert asked.status_code == 200
    assert asked.json()["email"] == old_email, "nothing changes until the link is opened"
    assert asked.json()["pending_email"] == "armando.new@arkivetesting.com"
    assert sent_mail[0]["to"] == "armando.new@arkivetesting.com"

    token = _link_token(sent_mail[0])
    assert client.get(f"/account/email-change/{token}").json() == {"status": "valid"}
    assert client.post(f"/account/email-change/{token}").status_code == 204

    assert client.get("/auth/me", headers=headers).json()["email"] == "armando.new@arkivetesting.com"
    # the old address is told
    assert sent_mail[1]["to"] == old_email
    # the link is spent, and the new address signs in
    assert client.get(f"/account/email-change/{token}").json() == {"status": "used"}
    assert client.post(f"/account/email-change/{token}").status_code == 400
    assert client.post(
        "/auth/login", json={"email": "armando.new@arkivetesting.com", "password": TEST_PASSWORD}
    ).status_code == 200


def test_an_email_change_needs_the_password_and_a_free_new_address(client, make_user, evaluator, sent_mail):
    make_user("taken@arkivetesting.com", UserRole.applicant)
    headers = auth_headers(client, evaluator.email)

    def ask(new_email, password=TEST_PASSWORD):
        return client.post(
            "/account/email-change", headers=headers, json={"new_email": new_email, "current_password": password}
        )

    assert ask("fresh@arkivetesting.com", password="wrong-password").status_code == 403
    assert ask("TAKEN@arkivetesting.com").status_code == 409
    assert ask(evaluator.email.upper()).status_code == 422
    assert sent_mail == []


def test_a_newer_request_or_a_cancellation_retires_the_old_link(client, evaluator, sent_mail):
    headers = auth_headers(client, evaluator.email)
    body = {"current_password": TEST_PASSWORD}

    client.post("/account/email-change", headers=headers, json={**body, "new_email": "first@arkivetesting.com"})
    client.post("/account/email-change", headers=headers, json={**body, "new_email": "second@arkivetesting.com"})
    first, second = _link_token(sent_mail[0]), _link_token(sent_mail[1])

    assert client.get(f"/account/email-change/{first}").json() == {"status": "used"}

    cancelled = client.delete("/account/email-change", headers=headers)
    assert cancelled.json()["pending_email"] is None
    assert client.post(f"/account/email-change/{second}").status_code == 400


def test_an_expired_link_changes_nothing(client, db_session, evaluator, sent_mail):
    headers = auth_headers(client, evaluator.email)
    client.post(
        "/account/email-change",
        headers=headers,
        json={"new_email": "late@arkivetesting.com", "current_password": TEST_PASSWORD},
    )
    for token in db_session.query(EmailChangeToken).filter_by(user_id=evaluator.id):
        token.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.flush()
    raw = _link_token(sent_mail[0])

    assert client.get(f"/account/email-change/{raw}").json() == {"status": "expired"}
    assert client.post(f"/account/email-change/{raw}").status_code == 400
    assert client.get("/auth/me", headers=headers).json()["email"] == evaluator.email


def test_confirming_refuses_an_address_someone_took_in_the_meantime(client, make_user, evaluator, sent_mail):
    headers = auth_headers(client, evaluator.email)
    client.post(
        "/account/email-change",
        headers=headers,
        json={"new_email": "race@arkivetesting.com", "current_password": TEST_PASSWORD},
    )
    make_user("race@arkivetesting.com", UserRole.applicant)

    assert client.post(f"/account/email-change/{_link_token(sent_mail[0])}").status_code == 409


def test_too_many_confirmation_emails_are_refused(client, evaluator, sent_mail, monkeypatch):
    monkeypatch.setattr(account_router, "EMAIL_CHANGE_MAX_REQUESTS", 2)
    headers = auth_headers(client, evaluator.email)

    codes = [
        client.post(
            "/account/email-change",
            headers=headers,
            json={"new_email": f"n{i}@arkivetesting.com", "current_password": TEST_PASSWORD},
        ).status_code
        for i in range(3)
    ]

    assert codes == [200, 200, 429]
