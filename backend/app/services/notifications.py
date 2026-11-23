"""In-app notifications: sending one (notify) and reading a person's
inbox, shared by all three roles."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models.candidate_application import CandidateApplication
from app.models.enums import UserRole
from app.models.job_requisition import JobRequisition
from app.models.notification import Notification
from app.models.user import User
from app.schemas.user import avatar_url
from app.services.account_erasure import is_erased

# What a notice is about -- drives the Notifications page's filter and
# icon. "system" is anything else, and
# what every notice written before kinds existed reads as.
NotificationKind = Literal["schedule", "decision", "application", "system"]
NOTIFICATION_KINDS: tuple[str, ...] = ("schedule", "decision", "application", "system")

# The inbox's folders. A kind is a filter inside the inbox, not a folder
# of its own, so an archived schedule notice is only under Archived.
NotificationFolder = Literal["inbox", "unread", "archived"]
NOTIFICATION_FOLDERS: tuple[str, ...] = ("inbox", "unread", "archived")

#: Who an applicant sees whenever a staff member acted. Applicants are
#: never told which HR admin or evaluator it was.
OFFICE_SENDER = "MSEUF HR Office"
#: Who everyone sees for what ARKIVE did by itself.
SYSTEM_SENDER = "ARKIVE"
#: An erased account, as a sender. Its row stays (account_erasure), but
#: not who it was.
DELETED_SENDER = "Deleted user"

_ROLE_LABEL = {
    UserRole.hr_admin: "HR Admin",
    UserRole.evaluator: "Evaluator",
    UserRole.applicant: "Applicant",
}

# Links that open one application's page, for the HR admin, the
# applicant and the evaluator. A notice with one of these and no
# application left (a deleted job takes its applications with it) points
# at a page that no longer exists.
_APPLICATION_LINK_PREFIXES = ("/hr/applications/", "/applicant/applications/", "/evaluator/interviews/")


def notify(
    db: Session,
    *,
    user_id: int,
    title: str,
    message: str,
    actor_id: int | None,
    application_id: int | None,
    link: str | None = None,
    kind: NotificationKind = "system",
) -> Notification:
    """Sends `user_id` a notice. `actor_id` is the person who did the
    thing, or None when ARKIVE did it by itself; `application_id` is what
    it is about, or None. Both are required, so no call site forgets.
    Caller owns db.commit()."""
    notification = Notification(
        user_id=user_id,
        actor_id=actor_id,
        title=title,
        message=message,
        application_id=application_id,
        link=link,
        kind=kind,
    )
    db.add(notification)
    return notification


# ---------------------------------------------------------------- reading


@dataclass(frozen=True)
class Sender:
    """Who a notice is shown as coming from. `kind` is "person" (a photo
    and name), "office" (the HR Office, with the ARKIVE mark) or "system"
    (ARKIVE itself)."""

    kind: Literal["person", "office", "system"]
    name: str
    role: str | None = None
    avatar_url: str | None = None


def sender_for(recipient: User, actor: User | None) -> Sender:
    """The rule for who a notice came from, by who is reading it.

    - Nobody acted (ARKIVE did it, or the notice predates senders):
      "ARKIVE", for everyone.
    - An applicant reading: "MSEUF HR Office" whenever someone else
      acted. Never the staff member's name, photo or email. Their own
      action (booking their own exam) reads as ARKIVE confirming it.
    - HR or an evaluator reading: the real person, with their role. An
      erased account is "Deleted user" with no photo; a switched-off one
      is still who it was, marked as deactivated.
    """
    if actor is None or actor.id == recipient.id:
        return Sender(kind="system", name=SYSTEM_SENDER)
    if recipient.role == UserRole.applicant:
        return Sender(kind="office", name=OFFICE_SENDER)
    if is_erased(actor):
        return Sender(kind="person", name=DELETED_SENDER)
    parts = [_ROLE_LABEL.get(actor.role, "Staff")]
    if actor.job_title:
        parts.append(actor.job_title)
    if not actor.is_active:
        parts.append("Deactivated")
    return Sender(
        kind="person",
        name=actor.full_name,
        role=" · ".join(parts),
        avatar_url=avatar_url(actor.avatar_file),
    )


def is_available(notification: Notification) -> bool:
    """False when the notice opens an application's page and that
    application is gone. The reading pane says "no longer available"
    instead of sending the person to a page that 404s."""
    if not notification.link or not notification.link.startswith(_APPLICATION_LINK_PREFIXES):
        return True
    return notification.application_id is not None


@dataclass(frozen=True)
class InboxRow:
    """One notice with everything its list item and reading pane show,
    fetched in the same query."""

    notification: Notification
    actor: User | None
    application: CandidateApplication | None
    requisition: JobRequisition | None
    candidate: User | None


def _inbox_select() -> tuple[Select, type[User]]:
    """The notice with its sender, application, job and candidate, all
    outer-joined: none of them is guaranteed to exist."""
    actor = aliased(User, name="actor")
    candidate = aliased(User, name="candidate")
    query = (
        select(Notification, actor, CandidateApplication, JobRequisition, candidate)
        .outerjoin(actor, actor.id == Notification.actor_id)
        .outerjoin(CandidateApplication, CandidateApplication.id == Notification.application_id)
        .outerjoin(JobRequisition, JobRequisition.id == CandidateApplication.requisition_id)
        .outerjoin(candidate, candidate.id == CandidateApplication.applicant_id)
    )
    return query, actor


def _like(term: str) -> str:
    # Escape the LIKE wildcards so "100%" searches for that, not everything.
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def list_inbox(
    db: Session,
    recipient: User,
    *,
    folder: NotificationFolder = "inbox",
    kind: str | None = None,
    q: str | None = None,
    before_id: int | None = None,
    limit: int = 50,
) -> tuple[list[InboxRow], bool]:
    """A page of the recipient's notices, newest first, and whether an
    older page exists. Paged by id, so new notices don't cause repeats.

    `q` searches the title, message and the sender name *this reader* is
    shown, so an applicant cannot find who acted by searching a staff
    name."""
    query, actor = _inbox_select()
    query = query.where(Notification.user_id == recipient.id)

    if folder == "archived":
        query = query.where(Notification.archived_at.is_not(None))
    else:
        query = query.where(Notification.archived_at.is_(None))
        if folder == "unread":
            query = query.where(Notification.read_at.is_(None))
    if kind is not None:
        query = query.where(Notification.kind == kind)

    term = (q or "").strip()
    if term:
        pattern = _like(term)
        matches = [Notification.title.ilike(pattern), Notification.message.ilike(pattern)]
        if recipient.role == UserRole.applicant:
            needle = term.lower()
            if needle in OFFICE_SENDER.lower():
                matches.append(Notification.actor_id.is_not(None) & (Notification.actor_id != recipient.id))
            if needle in SYSTEM_SENDER.lower():
                matches.append(or_(Notification.actor_id.is_(None), Notification.actor_id == recipient.id))
        else:
            matches.append(actor.full_name.ilike(pattern))
        query = query.where(or_(*matches))

    if before_id is not None:
        query = query.where(Notification.id < before_id)

    # one extra row says whether there is another page
    rows = db.execute(query.order_by(Notification.id.desc()).limit(limit + 1)).all()
    return [InboxRow(*row) for row in rows[:limit]], len(rows) > limit


def get_inbox_row(db: Session, recipient: User, notification_id: int) -> InboxRow | None:
    """One of the recipient's notices, or None -- for someone else's too,
    so a caller can't tell the two apart."""
    query, _actor = _inbox_select()
    row = db.execute(
        query.where(Notification.id == notification_id, Notification.user_id == recipient.id)
    ).first()
    return InboxRow(*row) if row else None


def inbox_unread_count(db: Session, recipient: User) -> int:
    """The bell's badge: unread notices still in the inbox."""
    return db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == recipient.id,
            Notification.read_at.is_(None),
            Notification.archived_at.is_(None),
        )
    ) or 0


@dataclass
class FolderCount:
    total: int = 0
    unread: int = 0


@dataclass
class FolderCounts:
    inbox: FolderCount
    archived: FolderCount
    # inside the inbox, by kind
    kinds: dict[str, FolderCount]


def folder_counts(db: Session, recipient: User) -> FolderCounts:
    """Every count the inbox's folder list shows, in one grouped query."""
    archived = Notification.archived_at.is_not(None)
    unread = Notification.read_at.is_(None)
    rows = db.execute(
        select(Notification.kind, archived, unread, func.count())
        .where(Notification.user_id == recipient.id)
        .group_by(Notification.kind, archived, unread)
    ).all()
    counts = FolderCounts(
        inbox=FolderCount(),
        archived=FolderCount(),
        kinds={kind: FolderCount() for kind in NOTIFICATION_KINDS},
    )
    for kind, is_archived, is_unread, n in rows:
        buckets = [counts.archived] if is_archived else [counts.inbox, counts.kinds.setdefault(kind, FolderCount())]
        for bucket in buckets:
            bucket.total += n
            if is_unread:
                bucket.unread += n
    return counts


# ---------------------------------------------------------------- changing


def mark_read(notification: Notification) -> None:
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)


def mark_unread(notification: Notification) -> None:
    notification.read_at = None


def archive(notification: Notification) -> None:
    """Out of the inbox. Archiving reads it too: an unread notice tucked
    away where no badge counts it would be unread forever."""
    now = datetime.now(timezone.utc)
    notification.archived_at = notification.archived_at or now
    notification.read_at = notification.read_at or now


def unarchive(notification: Notification) -> None:
    """Back in the inbox, as read -- it was read when it left."""
    notification.archived_at = None


def mark_inbox_read(db: Session, recipient: User) -> None:
    """Mark all as read: everything unread in the inbox."""
    db.execute(
        Notification.__table__.update()
        .where(
            Notification.user_id == recipient.id,
            Notification.read_at.is_(None),
            Notification.archived_at.is_(None),
        )
        .values(read_at=datetime.now(timezone.utc))
    )
