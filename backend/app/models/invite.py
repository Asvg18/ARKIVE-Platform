from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base
from app.models.mixins import TimestampMixin


class Invite(Base, TimestampMixin):
    """A pending (or resolved) staff account invitation -- how new
    hr_admin/evaluator accounts get provisioned.

    role is a plain string, validated at the API boundary. Status
    (pending/accepted/expired/revoked) is computed from the timestamps,
    never stored.
    """

    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[str] = mapped_column(String(20))

    # SHA-256 hex digest of the raw token — the raw token is shown to HR
    # once (in the create response) and never stored, same principle as
    # a password reset token.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Null for the invitation the first-admin setup step sends
    # (scripts/create_first_admin.py): on a fresh installation there is
    # nobody yet to have sent it. User Management shows those as sent by
    # "ARKIVE setup".
    invited_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # hr_admin invitations only: the account is created as a super admin.
    super_admin: Mapped[bool] = mapped_column(default=False, server_default="false")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # When the invitation's link last went out by email -- null when it
    # never has (no mail server on this copy, or the server refused it),
    # in which case the link was only shown on screen to pass on by hand.
    # User Management shows which, per invitation, and offers a resend.
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
