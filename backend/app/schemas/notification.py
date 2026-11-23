from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class NotificationSender(BaseModel):
    """Who the notice is shown as coming from -- already decided for the
    reader (services/notifications.sender_for). An applicant's response
    never carries a staff member's name, photo or id."""

    kind: Literal["person", "office", "system"]
    name: str
    role: str | None = None
    avatar_url: str | None = None


class NotificationAbout(BaseModel):
    """The application a notice is about: the reading pane's About card."""

    application_id: int
    requisition_id: int
    candidate_name: str
    candidate_avatar_url: str | None = None
    job_title: str
    department: str


class NotificationRead(BaseModel):
    id: int
    title: str
    message: str
    link: str | None
    kind: str
    read_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    sender: NotificationSender
    about: NotificationAbout | None = None
    # False when the page this notice opens no longer exists (its job
    # was deleted); the reading pane says so instead of linking to it.
    available: bool = True


class NotificationListResponse(BaseModel):
    items: list[NotificationRead]
    # unread notices still in the inbox -- the bell's badge
    unread_count: int
    # whether older notices exist past this page -- the Notifications
    # page's "Load more"
    has_more: bool = False


class NotificationFolderCount(BaseModel):
    total: int
    unread: int


class NotificationCounts(BaseModel):
    """The inbox's folder list. Kinds count inside the inbox only."""

    inbox: NotificationFolderCount
    archived: NotificationFolderCount
    kinds: dict[str, NotificationFolderCount]
