from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base
from app.models.mixins import TimestampMixin


class PasswordResetToken(Base, TimestampMixin):
    """A single-use "set a new password" link.

    Only the SHA-256 digest is stored; the raw token exists only in the
    emailed link. Valid an hour, since the person is waiting for it.
    """

    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Set the moment the token is spent. Kept rather than deleted, so
    # "this link has already been used" is a thing the app can say
    # instead of the same "not found" a made-up token gets.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
