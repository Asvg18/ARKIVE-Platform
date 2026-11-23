from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base


class ExamSlot(Base):
    """One exam session a job offers: a date, a time window, a place and
    a number of seats, per exam stage (e.g. "examination_1"). HR creates
    them in batches on the job's page; the applicant picks one with free
    seats once they reach that exam stage, which books it at once and
    writes the real StageInstance.payload["schedule"].

    stage_type is a plain string, validated at the API boundary with
    dfa.is_exam_stage()."""

    __tablename__ = "exam_slots"

    id: Mapped[int] = mapped_column(primary_key=True)
    requisition_id: Mapped[int] = mapped_column(ForeignKey("job_requisitions.id"))
    stage_type: Mapped[str] = mapped_column(String(64))
    date: Mapped[str] = mapped_column(String(10))
    time: Mapped[str] = mapped_column(String(5))
    # end of the session's window; None on slots made before sessions had
    # one (they only ever had a start time)
    end_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    location: Mapped[str] = mapped_column(String(255))
    capacity: Mapped[int] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
