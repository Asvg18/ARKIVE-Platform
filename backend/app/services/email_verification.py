from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infra.config import settings
from app.models.email_verification import EmailVerificationToken
from app.models.user import User
from app.services.email import send_email_safely

VERIFICATION_VALIDITY = timedelta(hours=24)
logger = logging.getLogger(__name__)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def token_status(token: EmailVerificationToken | None) -> str:
    if token is None:
        return "unknown"
    if token.used_at is not None:
        return "used"
    if token.expires_at < datetime.now(timezone.utc):
        return "expired"
    return "valid"


def find_token(db: Session, raw_token: str) -> EmailVerificationToken | None:
    return db.scalar(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == hash_token(raw_token)
        )
    )


def issue_verification(db: Session, user: User) -> str:
    now = datetime.now(timezone.utc)
    for token in db.scalars(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.used_at.is_(None),
        )
    ).all():
        token.used_at = now
    raw_token = secrets.token_urlsafe(32)
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=now + VERIFICATION_VALIDITY,
        )
    )
    db.commit()
    link = f"{settings.frontend_base_url.rstrip('/')}/verify-email/{raw_token}"
    sent = send_email_safely(
        to=user.email,
        subject="Verify your ARKIVE email address",
        body=(
            f"Hello {user.full_name},\n\n"
            f"Verify your email address by opening:\n\n{link}\n\n"
            "This link expires in 24 hours.\n"
        ),
    )
    if not sent:
        logger.info("Email verification link for user %s (mail not sent): %s", user.id, link)
    return raw_token


def spend_token(db: Session, token: EmailVerificationToken) -> User:
    user = db.get(User, token.user_id)
    if user is None:
        raise ValueError("Email verification token points at a missing user")
    now = datetime.now(timezone.utc)
    user.email_verified_at = user.email_verified_at or now
    token.used_at = now
    db.commit()
    return user
