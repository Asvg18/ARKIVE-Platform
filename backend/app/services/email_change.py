"""Changing the email an account signs in with (request_change, then
confirm_change)."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.email_change import EmailChangeToken
from app.models.user import User
from app.services.email import send_email_safely

logger = logging.getLogger(__name__)

# A day. Nobody is locked out while this waits, and a new work address
# may not be set up to receive mail within the hour a reset allows.
EMAIL_CHANGE_VALIDITY = timedelta(hours=24)


class EmailTakenError(Exception):
    """Another account already signs in with that address."""


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def email_in_use(db: Session, email: str, *, excluding_user_id: int | None = None) -> bool:
    """Case-insensitively: two accounts that differ only by capitals would
    be one person's two sign-ins, and a reset could only reach one."""
    query = select(User.id).where(func.lower(User.email) == email.lower())
    if excluding_user_id is not None:
        query = query.where(User.id != excluding_user_id)
    return db.scalar(query) is not None


def pending_change(db: Session, user_id: int) -> EmailChangeToken | None:
    """The request still waiting to be confirmed, if any."""
    return db.scalar(
        select(EmailChangeToken)
        .where(
            EmailChangeToken.user_id == user_id,
            EmailChangeToken.used_at.is_(None),
            EmailChangeToken.expires_at > datetime.now(timezone.utc),
        )
        .order_by(EmailChangeToken.created_at.desc(), EmailChangeToken.id.desc())
        .limit(1)
    )


def cancel_pending(db: Session, user_id: int) -> None:
    """Retires every unconfirmed request, so only the newest can ever
    change anything. Does not commit."""
    now = datetime.now(timezone.utc)
    for token in db.scalars(
        select(EmailChangeToken).where(
            EmailChangeToken.user_id == user_id, EmailChangeToken.used_at.is_(None)
        )
    ):
        token.used_at = now


def request_change(db: Session, *, user: User, new_email: str, confirm_url_base: str) -> EmailChangeToken:
    """Step 1 of 2: records the request and mails its link to the *new*
    address; only opening it makes the change, because the email is also
    the only address a password reset can reach. Raises
    EmailTakenError when another account already uses it -- the same
    answer signup already gives anyone, so it reveals nothing new."""
    if email_in_use(db, new_email, excluding_user_id=user.id):
        raise EmailTakenError(new_email)

    cancel_pending(db, user.id)
    raw_token = secrets.token_urlsafe(32)
    token = EmailChangeToken(
        user_id=user.id,
        new_email=new_email,
        token_hash=hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + EMAIL_CHANGE_VALIDITY,
    )
    db.add(token)
    db.commit()
    db.refresh(token)

    link = f"{confirm_url_base.rstrip('/')}/confirm-email/{raw_token}"
    sent = send_email_safely(
        to=new_email,
        subject="Confirm your new ARKIVE sign-in email",
        body=(
            f"Hello {user.full_name},\n\n"
            "You asked to sign in to ARKIVE with this email address from now on. "
            "Open the link below to confirm it:\n\n"
            f"{link}\n\n"
            "The link works once and expires in 24 hours. Until you open it, "
            f"you keep signing in with {user.email}.\n\n"
            "If this wasn't you, ignore this message. Nothing changes.\n"
        ),
    )
    if not sent:
        # The only record of the link when mail isn't set up (a workshop
        # machine with no SMTP): without it the change could never be
        # confirmed there at all.
        logger.info("Email change link for user %s (mail not sent): %s", user.id, link)
    return token


def find_token(db: Session, raw_token: str) -> EmailChangeToken | None:
    return db.scalar(select(EmailChangeToken).where(EmailChangeToken.token_hash == hash_token(raw_token)))


def token_status(token: EmailChangeToken | None) -> str:
    if token is None:
        return "unknown"
    if token.used_at is not None:
        return "used"
    if token.expires_at < datetime.now(timezone.utc):
        return "expired"
    return "valid"


def confirm_change(db: Session, token: EmailChangeToken) -> User:
    """Makes the change and spends the link in one transaction, then lets
    the old address know. Re-checks the address, since another account
    may have taken it while the link sat in a mailbox."""
    user = db.get(User, token.user_id)
    if user is None:  # pragma: no cover - the FK makes this unreachable
        raise ValueError("Email change token points at a user that no longer exists")
    if email_in_use(db, token.new_email, excluding_user_id=user.id):
        raise EmailTakenError(token.new_email)

    old_email = user.email
    user.email = token.new_email
    cancel_pending(db, user.id)
    db.commit()
    db.refresh(user)

    # The heads-up to the address that just stopped working. If the
    # change wasn't theirs, this is how they find out.
    send_email_safely(
        to=old_email,
        subject="Your ARKIVE sign-in email was changed",
        body=(
            f"Hello {user.full_name},\n\n"
            f"Your ARKIVE account now signs in with {user.email} instead of this address.\n\n"
            "If you didn't make this change, contact the university HR office right away.\n"
        ),
    )
    return user
