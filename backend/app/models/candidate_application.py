from sqlalchemy import Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base
from app.models.enums import ApplicationStatus, StageType
from app.models.mixins import TimestampMixin


class CandidateApplication(Base, TimestampMixin):
    __tablename__ = "candidate_applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    applicant_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    requisition_id: Mapped[int] = mapped_column(ForeignKey("job_requisitions.id"))

    # denormalized for fast list views (HR dashboard table) -- derived
    # data, not a source of truth. every write here must happen in the
    # same transaction as the StageInstance/StageHistory update that
    # changes it, or the two drift out of sync.
    current_stage: Mapped[StageType | None] = mapped_column(
        Enum(StageType, name="stage_type"), nullable=True
    )

    # Hire/reject outcome — deliberately independent of current_stage/the
    # DFA (see ApplicationStatus). HR can set this at any stage.
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, name="application_status"),
        default=ApplicationStatus.active,
    )
