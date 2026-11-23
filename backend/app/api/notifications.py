"""In-app notification routes for every role, always scoped to the
caller's own user_id (rules in app.services.notifications)."""

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.infra.db import get_db
from app.infra.deps import get_current_user
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import (
    NotificationAbout,
    NotificationCounts,
    NotificationFolderCount,
    NotificationListResponse,
    NotificationRead,
    NotificationSender,
)
from app.schemas.user import avatar_url
from app.services import notifications as inbox
from app.services.notifications import NOTIFICATION_FOLDERS, NOTIFICATION_KINDS, InboxRow

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _to_read(row: InboxRow, recipient: User) -> NotificationRead:
    n = row.notification
    sender = inbox.sender_for(recipient, row.actor)
    about = None
    if row.application is not None and row.requisition is not None and row.candidate is not None:
        about = NotificationAbout(
            application_id=row.application.id,
            requisition_id=row.requisition.id,
            candidate_name=row.candidate.full_name,
            candidate_avatar_url=avatar_url(row.candidate.avatar_file),
            job_title=row.requisition.title,
            department=row.requisition.department,
        )
    return NotificationRead(
        id=n.id,
        title=n.title,
        message=n.message,
        link=n.link,
        kind=n.kind,
        read_at=n.read_at,
        archived_at=n.archived_at,
        created_at=n.created_at,
        sender=NotificationSender(
            kind=sender.kind, name=sender.name, role=sender.role, avatar_url=sender.avatar_url
        ),
        about=about,
        available=inbox.is_available(n),
    )


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    folder: str = "inbox",
    kind: str | None = None,
    q: str | None = Query(None, max_length=100),
    before_id: int | None = None,
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationListResponse:
    """Newest first. The bell takes the first few of the inbox; the
    Notifications page picks a folder (`inbox`, `unread`, `archived`),
    narrows the inbox by `kind`, searches with `q`, and pages back with
    `before_id` -- the id of the oldest notice it already has."""
    if folder not in NOTIFICATION_FOLDERS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unknown notification folder.")
    if kind is not None and kind not in NOTIFICATION_KINDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unknown notification kind.")
    rows, has_more = inbox.list_inbox(
        db, user, folder=folder, kind=kind, q=q, before_id=before_id, limit=limit
    )
    return NotificationListResponse(
        items=[_to_read(row, user) for row in rows],
        unread_count=inbox.inbox_unread_count(db, user),
        has_more=has_more,
    )


@router.get("/counts", response_model=NotificationCounts)
def notification_counts(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationCounts:
    """The folder list's counts: the inbox and each kind in it, and the
    archive -- each as a total and how many are unread."""
    counts = inbox.folder_counts(db, user)

    def one(c: inbox.FolderCount) -> NotificationFolderCount:
        return NotificationFolderCount(total=c.total, unread=c.unread)

    return NotificationCounts(
        inbox=one(counts.inbox),
        archived=one(counts.archived),
        kinds={kind: one(c) for kind, c in counts.kinds.items()},
    )


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    inbox.mark_inbox_read(db, user)
    db.commit()


def _own_row(db: Session, user: User, notification_id: int) -> InboxRow:
    row = inbox.get_inbox_row(db, user, notification_id)
    # 404, not 403, for a notification that exists but isn't the
    # requester's — matches this codebase's existing resource-ownership
    # convention (never confirm/deny existence via the wrong status code).
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return row


def _change(
    db: Session, user: User, notification_id: int, change: Callable[[Notification], None]
) -> NotificationRead:
    row = _own_row(db, user, notification_id)
    change(row.notification)
    db.commit()
    return _to_read(row, user)


@router.get("/{notification_id}", response_model=NotificationRead)
def get_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationRead:
    """One notice, for the reading pane opened from a link (`?n=`) whose
    notice isn't on the page of the list already loaded."""
    return _to_read(_own_row(db, user, notification_id), user)


@router.post("/{notification_id}/read", response_model=NotificationRead)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationRead:
    return _change(db, user, notification_id, inbox.mark_read)


@router.post("/{notification_id}/unread", response_model=NotificationRead)
def mark_notification_unread(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationRead:
    return _change(db, user, notification_id, inbox.mark_unread)


@router.post("/{notification_id}/archive", response_model=NotificationRead)
def archive_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationRead:
    return _change(db, user, notification_id, inbox.archive)


@router.post("/{notification_id}/unarchive", response_model=NotificationRead)
def unarchive_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationRead:
    return _change(db, user, notification_id, inbox.unarchive)
