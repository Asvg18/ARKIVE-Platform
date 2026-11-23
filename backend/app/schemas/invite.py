from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.auth import Password

InviteRole = Literal["hr_admin", "evaluator"]
InviteStatus = Literal["pending", "accepted", "expired", "revoked"]


class InviteCreateRequest(BaseModel):
    email: EmailStr
    role: InviteRole
    # hr_admin only: the account is created as a super admin.
    super_admin: bool = False


class InviteRead(BaseModel):
    id: int
    email: str
    role: str
    status: InviteStatus
    super_admin: bool = False
    # "ARKIVE setup" for the invitation the first-admin setup step sent.
    invited_by_name: str
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
    # When the link last went out by email; null = it never did, and was
    # only shown on screen to pass on by hand.
    emailed_at: datetime | None = None


class InviteCreated(InviteRead):
    """The raw token is only ever present here — shown once, right after
    creation, same one-time-reveal precedent as the old
    EvaluatorAccountCreated.temp_password."""

    token: str
    # Whether the invitation actually went out by email. False whenever
    # SMTP is unconfigured or the send failed, which is the case the
    # link in this same response exists to cover -- so the screen can
    # say "sent to them" or "copy this and send it" rather than leaving
    # HR to guess which happened.
    emailed: bool


class InviteStatusRead(BaseModel):
    """Public, unauthenticated read for the accept-invite page — just
    enough to render "you're invited as ROLE" without exposing anything
    else about the invite (who sent it, other pending invites, etc.)."""

    email: str
    role: str
    status: InviteStatus
    super_admin: bool = False


class InvitationEmailRead(BaseModel):
    """Whether this copy of ARKIVE can email invitations at all, so User
    Management can say so before anyone invites somebody -- rather than
    after, when the only sign is a link on the screen."""

    configured: bool
    # The address invitations come from, so HR can tell invitees what to
    # look for (and which sender to check their spam for).
    sender: str | None


class InviteAcceptRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    # Same rule as self-registration -- an invited HR admin is the person
    # most likely to be using a password manager, so this is the path the
    # 72-byte ceiling was most likely to be hit on.
    password: Password
