"""Create the first super admin of a fresh ARKIVE installation.

A new installation has no accounts at all, and applicants' sign-up can
only ever make applicants -- so nobody could open User Management to
invite anyone. This is the one way in. Whoever installs ARKIVE runs it
once, on the computer ARKIVE is installed on, with the email of the
person who will run HR's accounts (normally the head of the HR office):

    python -m scripts.create_first_admin hr.head@example.edu      (workshop, from backend/)
    docker exec -it arkive-prod-backend-1 python -m scripts.create_first_admin hr.head@example.edu   (showroom)

It sets no password. It sends the same invitation email every staff
member receives (services/staff_accounts.issue_invite), so the new
super admin chooses their own password and the person running this
never knows it. If mail isn't set up, it prints the link instead, to be
passed on by hand.

Once an organization has a super admin this refuses to run again,
because from then on User Management is where accounts are made. Adding
--again overrides that: it lists the current super admins and asks for
YES before doing anything. That is the emergency key if every super
admin is locked out, and how the team re-runs "day one" while testing.

If the address already belongs to an active HR admin, they are simply
made a super admin -- they proved the address when they joined. Any
other existing account (an evaluator, an applicant, a deactivated
account) is refused; one address is one account.
"""

import argparse
import sys
from typing import Callable

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infra.db import SessionLocal
from app.models.enums import UserRole
from app.models.user import User
from app.services import staff_accounts

_ROLE_NAMES = {
    UserRole.hr_admin: "an HR admin",
    UserRole.evaluator: "an evaluator",
    UserRole.applicant: "an applicant",
}

# Exit codes: 0 done, 1 refused (nothing changed), 2 the email itself is unusable.
DONE, REFUSED, BAD_EMAIL = 0, 1, 2


def run(
    db: Session,
    email: str,
    *,
    again: bool = False,
    assume_yes: bool = False,
    ask: Callable[[str], str] = input,
    say: Callable[[str], None] = print,
) -> int:
    """The whole step, with its input and output passed in so the tests
    can drive it without a terminal."""
    try:
        email = str(TypeAdapter(EmailStr).validate_python(email.strip()))
    except ValidationError:
        say(f"That doesn't look like an email address: {email!r}")
        return BAD_EMAIL

    current = staff_accounts.active_super_admins(db)
    if current and not again:
        say("ARKIVE already has a super admin:")
        for admin in current:
            say(f"  - {admin.full_name} <{admin.email}>")
        say("They can invite or promote people from User Management, in the HR portal.")
        say("If none of them can sign in any more, run this again with --again.")
        return REFUSED
    if current and not assume_yes:
        say("ARKIVE already has these super admins, and they will stay super admins:")
        for admin in current:
            say(f"  - {admin.full_name} <{admin.email}>")
        answer = ask(f"Type YES to make {email} a super admin as well: ")
        if answer.strip() != "YES":
            say("Nothing changed.")
            return REFUSED

    account = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    if account is not None:
        return _promote_existing(db, account, say)

    revoked = staff_accounts.revoke_pending_setup_invites(db)
    try:
        issued = staff_accounts.issue_invite(
            db,
            email=email,
            role=UserRole.hr_admin,
            invited_by=None,
            super_admin=True,
        )
    except staff_accounts.InviteRefused as exc:
        db.rollback()
        say(str(exc))
        return REFUSED

    if revoked:
        say(f"Cancelled {revoked} earlier setup invitation(s) that had not been accepted.")
    if issued.emailed:
        say(f"Invitation emailed to {issued.invite.email}.")
        say("They open it, choose their own name and password, and arrive as super admin.")
    else:
        say("ARKIVE could not send the email (mail isn't set up, or the mail server refused it).")
        say("Send this link to the new super admin yourself -- it works once and only for them:")
        say(issued.link)
    say("The link expires in 7 days. Running this again sends a fresh one and cancels this one.")
    return DONE


def _promote_existing(db: Session, account: User, say: Callable[[str], None]) -> int:
    if account.role == UserRole.hr_admin and account.is_active:
        if account.is_super_admin:
            say(f"{account.email} is already a super admin. Nothing changed.")
            return DONE
        account.is_super_admin = True
        db.commit()
        say(f"{account.full_name} <{account.email}> is now a super admin.")
        say("User Management appears in their HR portal the next time a page loads.")
        return DONE

    state = "" if account.is_active else " (deactivated)"
    say(
        f"{account.email} already belongs to {_ROLE_NAMES[account.role]} account{state}, "
        "and one email can only ever be one account. Use a different email."
    )
    return REFUSED


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.create_first_admin",
        description="Invite the first super admin of this ARKIVE installation.",
    )
    parser.add_argument("email", help="the new super admin's email (normally the head of HR)")
    parser.add_argument(
        "--again",
        action="store_true",
        help="run even though a super admin already exists (asks you to confirm)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="with --again: skip the confirmation question",
    )
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        return run(db, args.email, again=args.again, assume_yes=args.yes)
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
