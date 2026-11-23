"""Staff accounts by invite link: a super admin invites an email and
role, and the invitee accepts the single-use link, setting their own
password."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infra.config import settings
from app.infra.db import get_db
from app.infra.deps import require_super_admin
from app.infra.security import create_access_token, hash_password
from app.models.enums import UserRole
from app.models.invite import Invite
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.schemas.invite import (
    InvitationEmailRead,
    InviteAcceptRequest,
    InviteCreated,
    InviteCreateRequest,
    InviteRead,
    InviteStatusRead,
)
from app.schemas.user import StaffRead, WaitingInterviewRead
from app.services import staff_accounts
from app.services.email import email_configured
from app.services.email_change import email_in_use

# /hr/invites and /hr/staff are super-admin only; the /invites/{token}
# routes are deliberately unauthenticated (the invitee has no account yet)
router = APIRouter(tags=["invites"])

# What User Management shows as the sender of the invitation the
# first-admin setup step sends -- there was nobody yet to send it.
SETUP_SENDER = "ARKIVE setup"


def _invite_read(db: Session, invite: Invite) -> InviteRead:
    if invite.invited_by_id is None:
        invited_by_name = SETUP_SENDER
    else:
        inviter = db.get(User, invite.invited_by_id)
        invited_by_name = inviter.full_name if inviter else "(unknown)"
    return InviteRead(
        id=invite.id,
        email=invite.email,
        role=invite.role,
        status=staff_accounts.invite_status(invite),
        super_admin=invite.super_admin,
        invited_by_name=invited_by_name,
        created_at=invite.created_at,
        expires_at=invite.expires_at,
        accepted_at=invite.accepted_at,
        emailed_at=invite.emailed_at,
    )


@router.post("/hr/invites", response_model=InviteCreated, status_code=status.HTTP_201_CREATED)
def create_invite(
    body: InviteCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_super_admin),
) -> InviteCreated:
    try:
        issued = staff_accounts.issue_invite(
            db,
            email=str(body.email),
            role=UserRole(body.role),
            invited_by=user,
            super_admin=body.super_admin,
        )
    except staff_accounts.EmailAlreadyHasAccount as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    except staff_accounts.InviteRefused as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))

    read = _invite_read(db, issued.invite)
    return InviteCreated(**read.model_dump(), token=issued.token, emailed=issued.emailed)


@router.get("/hr/invites", response_model=list[InviteRead])
def list_invites(
    db: Session = Depends(get_db),
    _user: User = Depends(require_super_admin),
) -> list[InviteRead]:
    rows = db.scalars(select(Invite).order_by(Invite.created_at.desc())).all()
    return [_invite_read(db, row) for row in rows]


@router.post("/hr/invites/{invite_id}/revoke", response_model=InviteRead)
def revoke_invite(
    invite_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_super_admin),
) -> InviteRead:
    invite = db.get(Invite, invite_id)
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if staff_accounts.invite_status(invite) != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Only a pending invite can be revoked.")

    invite.revoked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(invite)
    return _invite_read(db, invite)


@router.post("/hr/invites/{invite_id}/resend", response_model=InviteCreated)
def resend_invite(
    invite_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_super_admin),
) -> InviteCreated:
    """Emails a still-open invitation again, with a new link (the old one
    stops working) and a new seven days. Also how an expired invitation
    is brought back."""
    invite = db.get(Invite, invite_id)
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite not found")
    try:
        issued = staff_accounts.resend_invite(db, invite, sent_by=user)
    except staff_accounts.EmailAlreadyHasAccount as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    except staff_accounts.InviteRefused as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))

    read = _invite_read(db, issued.invite)
    return InviteCreated(**read.model_dump(), token=issued.token, emailed=issued.emailed)


@router.get("/hr/invitation-email", response_model=InvitationEmailRead)
def invitation_email(_user: User = Depends(require_super_admin)) -> InvitationEmailRead:
    """Whether invitations can go out by email on this copy of ARKIVE.
    Never carries the mail server's login or password."""
    configured = email_configured()
    sender = (settings.smtp_from_email or settings.smtp_username) if configured else None
    return InvitationEmailRead(configured=configured, sender=sender)


@router.get("/hr/staff", response_model=list[StaffRead])
def list_staff(
    db: Session = Depends(get_db),
    _user: User = Depends(require_super_admin),
) -> list[StaffRead]:
    rows = db.scalars(
        select(User)
        .where(User.role.in_([UserRole.hr_admin, UserRole.evaluator]))
        .order_by(User.role, User.full_name)
    ).all()
    return [StaffRead.model_validate(u) for u in rows]


def _staff_member(db: Session, user_id: int) -> User:
    """A staff row by id, or 404. Never an applicant account."""
    user = db.get(User, user_id)
    if user is None or user.role not in (UserRole.hr_admin, UserRole.evaluator):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Staff member not found")
    return user


@router.get("/hr/staff/{user_id}/waiting-interviews", response_model=list[WaitingInterviewRead])
def staff_waiting_interviews(
    user_id: int,
    db: Session = Depends(get_db),
    _actor: User = Depends(require_super_admin),
) -> list[WaitingInterviewRead]:
    """Asked by the switch-off confirmation before it is answered, so HR
    sees which interviews this person still owes. Always empty for an HR
    admin, who is never assigned interviews."""
    target = _staff_member(db, user_id)
    return staff_accounts.waiting_interviews(db, target.id)


@router.post("/hr/staff/{user_id}/deactivate", response_model=StaffRead)
def deactivate_staff(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_super_admin),
) -> StaffRead:
    """Switches an account off (`is_active` False): sign-in and every
    request are refused. Deliberately not a delete, so the person's
    evaluations and history stay intact. Interviews still assigned do not
    block it; the confirmation lists them first."""
    target = _staff_member(db, user_id)

    # This also guarantees a super admin always remains: the actor is an
    # active super admin, so the last one could only be their own target.
    if target.id == actor.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="You cannot deactivate your own account.",
        )

    target.is_active = False
    db.commit()
    db.refresh(target)
    return StaffRead.model_validate(target)


@router.post("/hr/staff/{user_id}/reactivate", response_model=StaffRead)
def reactivate_staff(
    user_id: int,
    db: Session = Depends(get_db),
    _actor: User = Depends(require_super_admin),
) -> StaffRead:
    """The other half of deactivation -- someone back from leave, or an
    account switched off by mistake. Their password is unchanged, so
    they sign in exactly as before."""
    target = _staff_member(db, user_id)
    target.is_active = True
    db.commit()
    db.refresh(target)
    return StaffRead.model_validate(target)


@router.post("/hr/staff/{user_id}/grant-super-admin", response_model=StaffRead)
def grant_super_admin(
    user_id: int,
    db: Session = Depends(get_db),
    _actor: User = Depends(require_super_admin),
) -> StaffRead:
    """Lets another HR admin manage accounts too (a backup, or a
    handover)."""
    target = _staff_member(db, user_id)
    if target.role != UserRole.hr_admin:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only an HR admin can be a super admin.",
        )
    if not target.is_active:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This account is deactivated. Reactivate it first.",
        )
    target.is_super_admin = True
    db.commit()
    db.refresh(target)
    return StaffRead.model_validate(target)


@router.post("/hr/staff/{user_id}/remove-super-admin", response_model=StaffRead)
def remove_super_admin(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_super_admin),
) -> StaffRead:
    """The account stays an HR admin with every hiring page; it loses
    User Management only.

    Refused for yourself, which guarantees a super admin always
    remains."""
    target = _staff_member(db, user_id)
    if target.id == actor.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="You cannot remove your own super admin access. Ask another super admin to do it.",
        )
    target.is_super_admin = False
    db.commit()
    db.refresh(target)
    return StaffRead.model_validate(target)


@router.get("/invites/{token}", response_model=InviteStatusRead)
def get_invite_status(token: str, db: Session = Depends(get_db)) -> InviteStatusRead:
    invite = db.scalar(select(Invite).where(Invite.token_hash == staff_accounts.hash_token(token)))
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite not found")
    return InviteStatusRead(
        email=invite.email,
        role=invite.role,
        status=staff_accounts.invite_status(invite),
        super_admin=invite.super_admin,
    )


@router.post("/invites/{token}/accept", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def accept_invite(token: str, body: InviteAcceptRequest, db: Session = Depends(get_db)) -> TokenResponse:
    invite = db.scalar(select(Invite).where(Invite.token_hash == staff_accounts.hash_token(token)))
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite not found")

    invite_status = staff_accounts.invite_status(invite)
    if invite_status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"This invite is {invite_status}, not pending.")

    if email_in_use(db, invite.email):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A user with this email already exists.")

    user = User(
        email=invite.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=UserRole(invite.role),
        auth_provider="local",
        provisioning_source="setup" if invite.invited_by_id is None else "invite",
        is_super_admin=invite.super_admin and invite.role == UserRole.hr_admin.value,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    invite.accepted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    token_str = create_access_token(user_id=user.id, role=user.role.value)
    return TokenResponse(access_token=token_str)
