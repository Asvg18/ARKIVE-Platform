"""Account Settings -- a person's own name, photo, staff details and
sign-in email. Every route acts on the signed-in account only: there is
no user id in any path.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.infra import rate_limit
from app.infra.config import settings
from app.infra.db import get_db
from app.infra.deps import get_current_user
from app.infra.security import verify_password
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import (
    DeleteAccountRequest,
    EmailChangeRequest,
    EmailChangeStatus,
    ProfileUpdate,
    UserRead,
)
from app.services import account_erasure, email_change
from app.services.file_storage import (
    AVATAR_MEDIA_TYPES,
    MAX_AVATAR_BYTES,
    delete_avatar_file,
    resolve_avatar_path,
    save_avatar_file,
    sniff_avatar_format,
)

router = APIRouter(prefix="/account", tags=["account"])

# No sign-in on purpose -- an <img> cannot send one. See file_storage's
# note on profile photos for why the random file name is the key.
avatar_router = APIRouter(prefix="/avatars", tags=["account"])

STAFF_ROLES = {UserRole.hr_admin, UserRole.evaluator}

# How many confirmation emails one account can trigger in an hour --
# enough for a typo and a retry or two, not enough to use ARKIVE to
# flood somebody else's inbox.
EMAIL_CHANGE_MAX_REQUESTS = 5
EMAIL_CHANGE_WINDOW_SECONDS = 60 * 60


def account_read(db: Session, user: User) -> UserRead:
    """The account as the top bar and the settings page see it."""
    pending = email_change.pending_change(db, user.id)
    return UserRead.model_validate(user).model_copy(
        update={"pending_email": pending.new_email if pending else None}
    )


@router.patch("/profile", response_model=UserRead)
def update_profile(
    body: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserRead:
    changes = body.cleaned()

    if "full_name" in changes and not changes["full_name"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Your name can't be empty.")

    staff_fields = {k: v for k, v in changes.items() if k in ("job_title", "department")}
    if current_user.role not in STAFF_ROLES and any(staff_fields.values()):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Job title and department are for HR and evaluator accounts.",
        )

    for key, value in changes.items():
        setattr(current_user, key, value)
    db.commit()
    db.refresh(current_user)
    return account_read(db, current_user)


@router.put("/avatar", response_model=UserRead)
async def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserRead:
    # The declared size first, as infra/uploads does, so an obvious
    # oversize is refused unread; then one byte past the limit is read,
    # which is enough to know without holding a huge upload in memory.
    if file.size is not None and file.size > MAX_AVATAR_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            detail="That photo is too large. Please use one under 2 MB.",
        )
    data = await file.read(MAX_AVATAR_BYTES + 1)
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            detail="That photo is too large. Please use one under 2 MB.",
        )
    image_format = sniff_avatar_format(data)
    if image_format is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Please upload a JPG, PNG or WebP image.",
        )

    previous = current_user.avatar_file
    current_user.avatar_file = save_avatar_file(data, image_format)
    db.commit()
    # Only once the new one is recorded -- a failed commit must not leave
    # the account pointing at a file that was just deleted.
    delete_avatar_file(previous)
    db.refresh(current_user)
    return account_read(db, current_user)


@router.delete("/avatar", response_model=UserRead)
def remove_avatar(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserRead:
    previous = current_user.avatar_file
    current_user.avatar_file = None
    db.commit()
    delete_avatar_file(previous)
    db.refresh(current_user)
    return account_read(db, current_user)


@router.post("/email-change", response_model=UserRead)
def request_email_change(
    body: EmailChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserRead:
    """Sends a confirmation link to the new address. The account keeps
    signing in with its current email until that link is opened."""
    attempt_key = f"email-change|{current_user.id}"
    send_key = f"email-change-send|{current_user.id}"

    # Same order as change-password: refuse a locked-out caller before
    # spending time on a bcrypt check.
    if rate_limit.seconds_until_retry(attempt_key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many incorrect attempts. Try again in a few minutes.",
        )
    if not verify_password(body.current_password, current_user.hashed_password):
        rate_limit.record_attempt(attempt_key)
        # 403, not 401: the client signs out on any 401.
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="The password you entered is incorrect.")
    rate_limit.clear(attempt_key)

    new_email = str(body.new_email).strip()
    if new_email.lower() == current_user.email.lower():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="That's already your sign-in email.")

    if rate_limit.seconds_until_retry(
        send_key, max_attempts=EMAIL_CHANGE_MAX_REQUESTS, window_seconds=EMAIL_CHANGE_WINDOW_SECONDS
    ):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many confirmation emails sent in the last hour. Try again later.",
        )

    try:
        email_change.request_change(
            db, user=current_user, new_email=new_email, confirm_url_base=settings.frontend_base_url
        )
    except email_change.EmailTakenError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Another account already uses that email.")
    rate_limit.record_attempt(send_key, window_seconds=EMAIL_CHANGE_WINDOW_SECONDS)
    return account_read(db, current_user)


@router.delete("/email-change", response_model=UserRead)
def cancel_email_change(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserRead:
    email_change.cancel_pending(db, current_user.id)
    db.commit()
    return account_read(db, current_user)


# The word the person types to confirm, as the last warning before it.
DELETE_CONFIRMATION = "DELETE"


@router.post("/delete", status_code=status.HTTP_204_NO_CONTENT)
def delete_own_account(
    body: DeleteAccountRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """An applicant deleting their own account: their open applications
    are withdrawn and everything that identifies them is erased, while
    HR keeps the record that the applications happened. See
    services/account_erasure for exactly what goes and what stays.

    Staff are refused -- another HR admin closes their account."""
    if current_user.role != UserRole.applicant:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Staff accounts are closed by an HR admin from User Management.",
        )

    attempt_key = f"delete-account|{current_user.id}"
    # Same order as change-password: refuse a locked-out caller before
    # spending time on a bcrypt check.
    if rate_limit.seconds_until_retry(attempt_key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many incorrect attempts. Try again in a few minutes.",
        )
    if not verify_password(body.current_password, current_user.hashed_password):
        rate_limit.record_attempt(attempt_key)
        # 403, not 401: the client signs out on any 401.
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="The password you entered is incorrect.")
    rate_limit.clear(attempt_key)

    if body.confirm.strip() != DELETE_CONFIRMATION:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Type {DELETE_CONFIRMATION} to confirm.",
        )

    files = account_erasure.erase_applicant(db, current_user)
    db.commit()
    # Only once the erasure is saved -- see erase_applicant.
    account_erasure.delete_files(files)


@router.get("/email-change/{token}", response_model=EmailChangeStatus)
def email_change_status(token: str, db: Session = Depends(get_db)) -> EmailChangeStatus:
    """Lets the confirmation page say a link is stale before offering to
    confirm it. No sign-in: the link is opened from the new mailbox,
    possibly on another device."""
    return EmailChangeStatus(status=email_change.token_status(email_change.find_token(db, token)))


@router.post("/email-change/{token}", status_code=status.HTTP_204_NO_CONTENT)
def confirm_email_change(token: str, db: Session = Depends(get_db)) -> None:
    """Opening the link proves the new address is real and reachable,
    which is all this step needs to establish; the password was checked
    when the change was asked for. Deliberately does not sign anyone in."""
    found = email_change.find_token(db, token)
    state = email_change.token_status(found)
    if found is None or state != "valid":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "unknown": "This confirmation link is not valid.",
                "used": "This confirmation link has already been used or was replaced by a newer one.",
                "expired": "This confirmation link has expired. Ask for a new one from Account Settings.",
            }[state],
        )
    try:
        email_change.confirm_change(db, found)
    except email_change.EmailTakenError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Another account started using this email in the meantime, so it can't be changed to it.",
        )


@avatar_router.get("/{name}")
def get_avatar(name: str) -> FileResponse:
    path = resolve_avatar_path(name)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")
    return FileResponse(
        path,
        media_type=AVATAR_MEDIA_TYPES[path.suffix.lstrip(".")],
        # A photo's name changes whenever the photo does, so a cached copy
        # can never go stale.
        headers={"Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"},
    )
