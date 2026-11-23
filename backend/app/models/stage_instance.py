from datetime import datetime

from sqlalchemy import JSON, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base
from app.models.enums import StageStatus, StageType


class StageInstance(Base):
    __tablename__ = "stage_instances"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_applications.id")
    )

    stage_type: Mapped[StageType] = mapped_column(
        Enum(StageType, name="stage_type")
    )
    status: Mapped[StageStatus] = mapped_column(
        Enum(StageStatus, name="stage_status"), default=StageStatus.pending
    )
    # shape depends on stage_type -- an examination stage's payload
    # holds a score, an interview stage's holds a transcript ref. no
    # shared shape to model, so JSON instead of per-stage tables.
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # the evaluator assigned to this interview round (interview_* stages
    # only); it is also what scopes what an evaluator can see
    assigned_evaluator_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
