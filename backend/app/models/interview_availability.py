from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base


class InterviewAvailability(Base):
    """One range of time an evaluator can interview in, for one candidate's
    interview round they are assigned to. HR cuts these into fixed slots by
    the round's length and sends the ones it wants to the applicant, who
    picks one.

    Kept per evaluator: if HR reassigns the round, only the assigned
    evaluator's ranges are read. Plain date/time strings, like the other
    scheduling tables."""

    __tablename__ = "interview_availability"

    id: Mapped[int] = mapped_column(primary_key=True)
    stage_instance_id: Mapped[int] = mapped_column(ForeignKey("stage_instances.id"), index=True)
    evaluator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    date: Mapped[str] = mapped_column(String(10))
    start_time: Mapped[str] = mapped_column(String(5))
    end_time: Mapped[str] = mapped_column(String(5))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
