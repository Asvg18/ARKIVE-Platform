from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base
from app.models.mixins import TimestampMixin


class JobDescriptionVersion(Base, TimestampMixin):
    """One version of a job opening's description: the text applicants
    are scored against, and the document it came from.

    The requisition's own columns hold the current text; these rows are
    the history behind it. Version 1 is what the job was created with, and
    the one with no `replaced_at` is in force.

    Each stored score records its version (SkillMatchResult.jd_version),
    and a replacement clears the cached embedding (services/
    job_descriptions). Nobody is re-scored.
    """

    __tablename__ = "job_description_versions"
    __table_args__ = (UniqueConstraint("requisition_id", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    requisition_id: Mapped[int] = mapped_column(ForeignKey("job_requisitions.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)

    # Null when the text was typed by hand, and for versions recorded
    # before the PDF was kept (every job created before this table).
    original_filename: Mapped[str | None] = mapped_column(String(255), default=None)
    stored_path: Mapped[str | None] = mapped_column(String(512), default=None)
    file_size: Mapped[int | None] = mapped_column(Integer, default=None)

    # A frozen copy of the text this version put in force.
    description: Mapped[str | None] = mapped_column(Text, default=None)
    qualifications: Mapped[str | None] = mapped_column(Text, default=None)
    requirements: Mapped[str | None] = mapped_column(Text, default=None)
    additional_sections: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))

    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    # HR's reason for replacing the previous version, if they gave one.
    change_note: Mapped[str | None] = mapped_column(Text, default=None)
    replaced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
