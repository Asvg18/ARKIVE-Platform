"""Staff accounts: who may be invited as what, and the invitation itself
(issue_invite)."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infra.config import settings
from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus, StageStatus, UserRole
from app.models.invite import Invite
from app.models.job_requisition import JobRequisition
from app.models.stage_instance import StageInstance
from app.models.user import User
from app.schemas.user import WaitingInterviewRead
from app.services.email import send_email_safely
from app.services.email_change import email_in_use
from app.services.stage_labels import resolve_stage_label

INVITE_VALIDITY = timedelta(days=7)

STAFF_ROLES = (UserRole.hr_admin, UserRole.evaluator)


class InviteRefused(Exception):
    """An invitation that cannot be sent. The message is written for the
    person who asked, and the API shows it as it is."""


class EmailAlreadyHasAccount(InviteRefused):
    """Someone already signs in with that address -- one address, one
    account, whatever its role."""


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def invite_status(invite: Invite) -> str:
    """Computed rather than stored, so it can never drift from the
    timestamps it is read from."""
    if invite.accepted_at is not None:
        return "accepted"
    if invite.revoked_at is not None:
        return "revoked"
    if invite.expires_at < datetime.now(timezone.utc):
        return "expired"
    return "pending"


# --------------------------------------------------------------------
# Invitations
# --------------------------------------------------------------------


@dataclass
class IssuedInvite:
    invite: Invite
    # The raw token exists only here, in memory -- the table keeps its
    # SHA-256 digest -- so the link can be shown once and never again.
    token: str
    link: str
    emailed: bool


def issue_invite(
    db: Session,
    *,
    email: str,
    role: UserRole,
    invited_by: User | None,
    super_admin: bool = False,
) -> IssuedInvite:
    """Creates (or renews) the invitation for `email` and emails its link.
    Used by User Management and the first-admin setup step, so the first
    super admin is created by the same rules as every later invite.

    `invited_by` is None only for the first-admin setup step. Raises
    InviteRefused, with a message fit for the screen, when the address
    or the combination asked for is not allowed.

    Re-inviting an address whose invitation is still pending renews that
    one row -- new link, new expiry, the role now asked for -- instead of
    leaving two live links to two different roles."""
    email = email.strip()
    if role not in STAFF_ROLES:
        raise InviteRefused("Only HR admins and evaluators are invited; applicants sign up themselves.")
    if super_admin and role != UserRole.hr_admin:
        raise InviteRefused("Only an HR admin can be a super admin.")
    if email_in_use(db, email):
        raise EmailAlreadyHasAccount("A user with this email already exists.")

    invite = db.scalar(
        select(Invite).where(
            func.lower(Invite.email) == email.lower(),
            Invite.accepted_at.is_(None),
            Invite.revoked_at.is_(None),
        )
    )
    if invite is None:
        invite = Invite(email=email)
        db.add(invite)
    invite.email = email
    invite.role = role.value
    invite.super_admin = super_admin
    invite.invited_by_id = invited_by.id if invited_by is not None else None
    return _issue_link(db, invite, sender=invited_by)


def resend_invite(db: Session, invite: Invite, *, sent_by: User) -> IssuedInvite:
    """Sends a still-open invitation again, with a fresh link and seven
    days. The previous link stops working.

    Refused for an invitation that was accepted or revoked, and held to
    the same rule as a new one: the address may since have become an
    account."""
    status = invite_status(invite)
    if status not in ("pending", "expired"):
        raise InviteRefused(f"This invitation was {status}, so it can't be sent again.")
    if email_in_use(db, invite.email):
        raise EmailAlreadyHasAccount("A user with this email already exists.")
    return _issue_link(db, invite, sender=sent_by)


def _issue_link(db: Session, invite: Invite, *, sender: User | None) -> IssuedInvite:
    """A new link for `invite`, saved before anything is sent, then the
    email. The invitation is committed first on purpose: an unconfigured
    or unreachable mail server must never stop it existing, because the
    link is still perfectly usable by hand."""
    raw_token = secrets.token_urlsafe(32)
    invite.token_hash = hash_token(raw_token)
    invite.expires_at = datetime.now(timezone.utc) + INVITE_VALIDITY
    invite.emailed_at = None
    db.commit()
    db.refresh(invite)

    link = f"{settings.frontend_base_url.rstrip('/')}/accept-invite/{raw_token}"
    # send_email_safely never raises, and says whether it sent -- which is
    # recorded on the invitation, so User Management can show per
    # invitation whether it went out rather than leave HR to guess.
    subject, body = _invitation_email(invite, sender, link)
    emailed = send_email_safely(to=invite.email, subject=subject, body=body)
    if emailed:
        invite.emailed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(invite)
    return IssuedInvite(invite=invite, token=raw_token, link=link, emailed=emailed)


def _access_phrase(invite: Invite) -> str:
    if invite.role == UserRole.hr_admin.value:
        if invite.super_admin:
            return "a super admin (an HR administrator who also manages everyone's accounts)"
        return "an HR administrator"
    return "an evaluator"


def _invitation_email(invite: Invite, invited_by: User | None, link: str) -> tuple[str, str]:
    closing = (
        "The link works once and expires in seven days.\n\n"
        "If you were not expecting this, you can ignore this message. "
        "No account is created until the link is opened.\n"
    )
    if invited_by is None:
        return (
            "Set up your ARKIVE super admin account",
            "Hello,\n\n"
            "ARKIVE has been set up for your organization, and you have been named "
            "its super admin: the HR administrator who invites everyone else and "
            "manages their accounts. Open the link below to set your name and "
            f"password:\n\n{link}\n\n{closing}",
        )
    return (
        "You have been invited to ARKIVE",
        f"Hello,\n\n{invited_by.full_name} has invited you to ARKIVE as {_access_phrase(invite)}. "
        f"Open the link below to set your name and password:\n\n{link}\n\n{closing}",
    )


def revoke_pending_setup_invites(db: Session) -> int:
    """Retires every setup invitation still waiting, so a re-run of the
    setup step never leaves two live super admin links -- one of them
    perhaps sent to a mistyped address. Does not commit."""
    now = datetime.now(timezone.utc)
    revoked = 0
    for invite in db.scalars(
        select(Invite).where(
            Invite.invited_by_id.is_(None),
            Invite.accepted_at.is_(None),
            Invite.revoked_at.is_(None),
        )
    ):
        invite.revoked_at = now
        revoked += 1
    return revoked


# --------------------------------------------------------------------
# Reading staff
# --------------------------------------------------------------------


def active_super_admins(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(
                User.role == UserRole.hr_admin,
                User.is_super_admin.is_(True),
                User.is_active.is_(True),
            )
            .order_by(User.id)
        ).all()
    )


def waiting_interviews(db: Session, evaluator_id: int) -> list[WaitingInterviewRead]:
    """The interviews that would be left waiting if this evaluator's
    account were switched off: assigned to them, not yet evaluated, on a
    round that has not been closed, for a candidate still in the running
    (active, or flagged and awaiting HR's call).

    They do not block switching the account off; HR is shown them to
    reassign."""
    rows = db.execute(
        select(StageInstance, CandidateApplication, User.full_name, JobRequisition)
        .join(CandidateApplication, CandidateApplication.id == StageInstance.application_id)
        .join(User, User.id == CandidateApplication.applicant_id)
        .join(JobRequisition, JobRequisition.id == CandidateApplication.requisition_id)
        .where(
            StageInstance.assigned_evaluator_id == evaluator_id,
            StageInstance.status.in_([StageStatus.pending, StageStatus.in_progress]),
            CandidateApplication.status.in_([ApplicationStatus.active, ApplicationStatus.flagged]),
        )
        .order_by(StageInstance.id)
    ).all()
    return [
        WaitingInterviewRead(
            application_id=application.id,
            candidate_name=candidate_name,
            job_title=requisition.title,
            stage_label=resolve_stage_label(instance.stage_type.value, requisition),
        )
        for instance, application, candidate_name, requisition in rows
        if not (instance.payload or {}).get("evaluation")
    ]
