from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base
from app.models.enums import StageType


class StageHistory(Base):
    __tablename__ = "stage_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("candidate_applications.id"))

    # Null only for the very first transition an application ever makes.
    from_stage: Mapped[StageType | None] = mapped_column(
        Enum(StageType, name="stage_type"), nullable=True
    )
    to_stage: Mapped[StageType] = mapped_column(Enum(StageType, name="stage_type"))

    # stringified user id (e.g. "3"), or the literal "system" for
    # agent-driven transitions. not a FK because "system" isn't a real
    # user row.
    triggered_by: Mapped[str] = mapped_column(String(50))

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
