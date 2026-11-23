from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base
from app.models.mixins import TimestampMixin


class EmailChangeToken(Base, TimestampMixin):
    """A pending change of sign-in email, waiting for its link to be
    opened from the new mailbox.

    Only the SHA-256 digest is stored; spent once and kept, so "already
    used" can be said. Valid a day (nobody is locked out while it waits).
    """

    __tablename__ = "email_change_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    new_email: Mapped[str] = mapped_column(String(320))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Set when the link is followed -- or when a newer request or a
    # cancellation replaces it, which is why "used" is the word the
    # confirmation page uses for both.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
