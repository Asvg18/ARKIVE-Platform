from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base


class AgentRun(Base):
    """Execution log for the AI agents. Purely observational -- nothing
    in the app reads this back into its own behavior. Exists so an
    agent's activity is queryable evidence (which agent ran, on what,
    when) instead of only inferable from whatever it happened to write
    onto a StageInstance.payload."""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("candidate_applications.id"))
    agent_name: Mapped[str] = mapped_column(String(64))
    triggered_by_stage: Mapped[str] = mapped_column(String(64))
    output: Mapped[dict] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
