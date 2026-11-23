"""Issuing and spending "set a new password" links (issue_reset,
spend_token).
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infra.security import to_token_resolution
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.services.email import send_email_safely

logger = logging.getLogger(__name__)

# An hour. Long enough to walk away from the desk and come back, short
# enough that a link sitting in a mailbox stops being a key quickly.
RESET_VALIDITY = timedelta(hours=1)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def token_status(token: PasswordResetToken | None) -> str:
    if token is None:
        return "unknown"
    if token.used_at is not None:
        return "used"
    if token.expires_at < datetime.now(timezone.utc):
        return "expired"
    return "valid"


def find_token(db: Session, raw_token: str) -> PasswordResetToken | None:
    return db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(raw_token))
    )


def issue_reset(db: Session, *, email: str, reset_url_base: str) -> None:
    """Creates a reset link for `email` and sends it, when there is an
    account to send it to. Returns nothing either way: the form is open
    to the internet, so no caller may reveal whether an address has an
    account. The link is stored only as a digest (hash_token), spent
    once, and valid RESET_VALIDITY.

    A deactivated account gets no link. Someone who has been offboarded
    should not be able to let themselves back in, and the reset would
    fail at login anyway -- better to send nothing than a link that
    leads to a refusal."""
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        # Logged, because "the applicant says they never got the email"
        # is a real support question and this is the answer to it.
        logger.info("Password reset requested for an unusable address: %s", email)
        return

    # Any earlier link for this account stops working now. Asking a
    # second time usually means the first mail went astray, and leaving
    # both live widens the window for no benefit.
    _invalidate_outstanding(db, user.id)

    raw_token = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(timezone.utc) + RESET_VALIDITY,
        )
    )
    db.commit()

    link = f"{reset_url_base.rstrip('/')}/reset-password/{raw_token}"
    send_email_safely(
        to=user.email,
        subject="Reset your ARKIVE password",
        body=(
            f"Hello {user.full_name},\n\n"
            "Someone asked to reset the password for your ARKIVE account. "
            "Open the link below to choose a new one:\n\n"
            f"{link}\n\n"
            "The link works once and expires in one hour.\n\n"
            "If this wasn't you, you can ignore this message. Your "
            "password has not changed.\n"
        ),
    )


def _invalidate_outstanding(db: Session, user_id: int) -> None:
    now = datetime.now(timezone.utc)
    outstanding = db.scalars(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
        )
    ).all()
    for token in outstanding:
        token.used_at = now


def spend_token(db: Session, token: PasswordResetToken, hashed_password: str) -> User:
    """Sets the new password and burns the link, in one transaction --
    a password changed but a token left spendable would be a second
    chance for whoever else has the link."""
    user = db.get(User, token.user_id)
    if user is None:  # pragma: no cover - the FK makes this unreachable
        raise ValueError("Password reset token points at a user that no longer exists")

    # Whole seconds, matching a token's own resolution -- see
    # infra.security.to_token_resolution for why that matters here.
    now = to_token_resolution(datetime.now(timezone.utc))
    user.hashed_password = hashed_password
    # Ends every session that began on the old password. On this path
    # that is the whole point: someone resetting usually believes another
    # person is in their account.
    user.password_changed_at = now
    token.used_at = now
    db.commit()
    return user
