"""The first-admin setup step (scripts/create_first_admin.py): how a fresh
installation, which has no accounts at all, gets its first super admin.

Driven through `run`, the whole step with its terminal input and output
passed in. These tests run against the real development database, which
carries seeded accounts -- including a super admin -- so `fresh_install`
switches every super admin off inside the test's own transaction, which
is rolled back afterwards.
"""

import pytest
from sqlalchemy import select, update

from app.models.enums import UserRole
from app.models.invite import Invite
from app.models.user import User
from app.services import staff_accounts
from scripts.create_first_admin import BAD_EMAIL, DONE, REFUSED, run
from tests.conftest import TEST_PASSWORD, auth_headers


class Terminal:
    """Stands in for the person at the keyboard."""

    def __init__(self, answer: str = ""):
        self.lines: list[str] = []
        self.questions: list[str] = []
        self.answer = answer

    def say(self, line: str) -> None:
        self.lines.append(line)

    def ask(self, question: str) -> str:
        self.questions.append(question)
        return self.answer

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@pytest.fixture()
def fresh_install(db_session):
    db_session.execute(update(User).values(is_super_admin=False))
    db_session.flush()


def _setup_invites(db_session, email: str) -> list[Invite]:
    return list(
        db_session.scalars(
            select(Invite).where(Invite.email == email, Invite.invited_by_id.is_(None)).order_by(Invite.id)
        ).all()
    )


def _run(db_session, email, terminal, **kwargs):
    return run(db_session, email, ask=terminal.ask, say=terminal.say, **kwargs)


def test_a_fresh_installation_gets_a_super_admin_invitation(db_session, fresh_install):
    terminal = Terminal()

    assert _run(db_session, "head@arkivetesting.com", terminal) == DONE

    [invite] = _setup_invites(db_session, "head@arkivetesting.com")
    assert invite.role == UserRole.hr_admin.value
    assert invite.super_admin is True
    assert staff_accounts.invite_status(invite) == "pending"
    # mail is blanked in the suite, so the link is printed to pass on by hand
    assert "/accept-invite/" in terminal.text


def test_the_invitation_is_emailed_when_mail_works_and_the_link_is_not_printed(
    db_session, fresh_install, monkeypatch
):
    """Whoever runs the step should not end up holding a working link
    when the email already went -- the new super admin sets their own
    password, and nobody else should be able to."""
    sent: list[dict] = []
    monkeypatch.setattr(staff_accounts, "send_email_safely", lambda **kw: sent.append(kw) or True)
    terminal = Terminal()

    assert _run(db_session, "mailed-head@arkivetesting.com", terminal) == DONE

    assert len(sent) == 1
    assert sent[0]["to"] == "mailed-head@arkivetesting.com"
    assert sent[0]["subject"] == "Set up your ARKIVE super admin account"
    assert "/accept-invite/" in sent[0]["body"]
    assert "/accept-invite/" not in terminal.text


def test_accepting_it_creates_a_super_admin_and_user_management_names_the_sender(
    client, db_session, fresh_install
):
    terminal = Terminal()
    _run(db_session, "first-head@arkivetesting.com", terminal)
    token = next(line for line in terminal.lines if "/accept-invite/" in line).split("/accept-invite/")[1]

    accepted = client.post(f"/invites/{token}/accept", json={"full_name": "First Head", "password": TEST_PASSWORD})
    assert accepted.status_code == 201, accepted.text

    user = db_session.scalar(select(User).where(User.email == "first-head@arkivetesting.com"))
    assert user.role == UserRole.hr_admin
    assert user.is_super_admin is True
    assert user.provisioning_source == "setup"

    headers = auth_headers(client, "first-head@arkivetesting.com")
    listing = client.get("/hr/invites", headers=headers)
    assert listing.status_code == 200, listing.text
    row = next(i for i in listing.json() if i["email"] == "first-head@arkivetesting.com")
    assert row["invited_by_name"] == "ARKIVE setup"
    assert row["super_admin"] is True


def test_it_refuses_once_there_is_a_super_admin(db_session, hr_admin):
    terminal = Terminal()

    assert _run(db_session, "someone-else@arkivetesting.com", terminal) == REFUSED

    assert hr_admin.email in terminal.text
    assert "--again" in terminal.text
    assert _setup_invites(db_session, "someone-else@arkivetesting.com") == []


def test_again_asks_first_and_does_nothing_without_yes(db_session, hr_admin):
    terminal = Terminal(answer="no")

    assert _run(db_session, "replacement@arkivetesting.com", terminal, again=True) == REFUSED

    assert terminal.questions, "it must ask before acting"
    assert _setup_invites(db_session, "replacement@arkivetesting.com") == []


def test_again_with_yes_adds_a_super_admin_and_keeps_the_existing_one(db_session, hr_admin):
    terminal = Terminal(answer="YES")

    assert _run(db_session, "replacement@arkivetesting.com", terminal, again=True) == DONE

    assert len(_setup_invites(db_session, "replacement@arkivetesting.com")) == 1
    db_session.refresh(hr_admin)
    assert hr_admin.is_super_admin is True


def test_running_again_cancels_the_earlier_unaccepted_invitation(db_session, fresh_install):
    """A mistyped address must not leave a live super admin link behind."""
    _run(db_session, "typo-head@arkivetesting.com", Terminal())
    terminal = Terminal()
    _run(db_session, "real-head@arkivetesting.com", terminal)

    [first] = _setup_invites(db_session, "typo-head@arkivetesting.com")
    [second] = _setup_invites(db_session, "real-head@arkivetesting.com")
    assert staff_accounts.invite_status(first) == "revoked"
    assert staff_accounts.invite_status(second) == "pending"
    assert "Cancelled 1 earlier" in terminal.text


def test_an_existing_hr_admin_is_made_super_admin_directly(db_session, fresh_install, plain_hr_admin):
    terminal = Terminal()

    assert _run(db_session, plain_hr_admin.email, terminal) == DONE

    db_session.refresh(plain_hr_admin)
    assert plain_hr_admin.is_super_admin is True
    assert _setup_invites(db_session, plain_hr_admin.email) == []


def test_an_address_that_belongs_to_another_kind_of_account_is_refused(db_session, fresh_install, evaluator):
    terminal = Terminal()

    assert _run(db_session, evaluator.email, terminal) == REFUSED

    assert "evaluator" in terminal.text
    db_session.refresh(evaluator)
    assert evaluator.is_super_admin is False


def test_something_that_is_not_an_email_is_refused(db_session, fresh_install):
    assert _run(db_session, "not an email", Terminal()) == BAD_EMAIL
