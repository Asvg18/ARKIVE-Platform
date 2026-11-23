from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base


class RequisitionEvaluator(Base):
    """A job's pool of evaluators eligible to conduct its interview
    rounds -- HR builds this per job, then assigns a specific pool
    member to a specific candidate's round via StageInstance.
    assigned_evaluator_id. Pool membership alone grants no visibility;
    only an actual assignment does."""

    __tablename__ = "requisition_evaluators"
    __table_args__ = (UniqueConstraint("requisition_id", "evaluator_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    requisition_id: Mapped[int] = mapped_column(ForeignKey("job_requisitions.id"))
    evaluator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
