from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base
from app.models.enums import RescheduleRequestStatus


class InterviewRescheduleRequest(Base):
    """An evaluator's request to move a scheduled interview round they're
    assigned to, resolved by HR. Its own table, not the stage payload,
    because a request has its own lifecycle (pending -> approved/denied)."""

    __tablename__ = "interview_reschedule_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    stage_instance_id: Mapped[int] = mapped_column(ForeignKey("stage_instances.id"))
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))

    # plain strings, matching InterviewScheduleRequest's existing
    # convention (raw <input type=date/time> values) rather than making
    # this table the odd one out
    proposed_date: Mapped[str] = mapped_column(String(10))
    proposed_time: Mapped[str] = mapped_column(String(5))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[RescheduleRequestStatus] = mapped_column(
        Enum(RescheduleRequestStatus, name="reschedule_request_status"),
        default=RescheduleRequestStatus.pending,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
