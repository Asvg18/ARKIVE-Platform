from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base


class Notification(Base):
    """An in-app notification. No websockets: the bell polls
    (shared/hooks/useLiveRefresh), which also feeds the corner pop-ups."""

    __tablename__ = "notifications"
    # The inbox pages newest-first by id within one person's notices, and
    # every count is per person -- this keeps both off a full table scan.
    __table_args__ = (Index("ix_notifications_user_id_id", "user_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # who did the thing; null when ARKIVE did it (or for older notices).
    # Always the real person: what an applicant is shown instead is
    # decided on read (services.notifications.sender_for)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # A short subject line, "Reschedule request" or "Offer declined" --
    # the inbox's bold first line, with the message under it.
    title: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(Text)
    # The application this notice is about, which gives the reading
    # pane its candidate and job. Nulled (not cascaded) when a deleted
    # job takes its applications with it -- services/requisition_deletion
    # -- so the notice stays and reads as "no longer available".
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidate_applications.id"), nullable=True
    )
    # Frontend route to deep-link to when the notification is clicked,
    # e.g. "/evaluator/interviews/189". Nullable since not every
    # notification necessarily needs one.
    link: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # What the notice is about, for the Notifications page's filter and
    # icon: "schedule", "decision", "application" or "system" -- see
    # app.services.notifications.NotificationKind.
    kind: Mapped[str] = mapped_column(String(20), default="system", server_default="system")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Moved out of the inbox by the person. Archiving also reads it.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
