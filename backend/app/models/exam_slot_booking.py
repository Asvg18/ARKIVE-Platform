from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base
from app.models.enums import ExamBookingStatus


class ExamSlotBooking(Base):
    """One applicant's seat in an exam session, for one exam stage. An
    applicant's own pick, or HR's, is created approved; when the stage
    moves to another session, its earlier seat is marked denied. Older
    rows may still be `pending` proposals, which HR approves or denies.

    exam_slot_id is mutable: HR can approve a different eligible pick
    without a second row."""

    __tablename__ = "exam_slot_bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    exam_slot_id: Mapped[int] = mapped_column(ForeignKey("exam_slots.id"))
    application_id: Mapped[int] = mapped_column(ForeignKey("candidate_applications.id"))
    stage_instance_id: Mapped[int] = mapped_column(ForeignKey("stage_instances.id"))
    # every slot id the applicant multi-selected, not just the agent's
    # pick -- lets HR's approval UI offer an alternative from the
    # applicant's own eligible choices without a second round-trip
    applicant_selected_slot_ids: Mapped[list[int]] = mapped_column(JSON)
    status: Mapped[ExamBookingStatus] = mapped_column(
        Enum(ExamBookingStatus, name="exam_booking_status"), default=ExamBookingStatus.pending
    )

    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
