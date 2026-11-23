from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base
from app.models.mixins import TimestampMixin


class ApplicationResume(Base, TimestampMixin):


    __tablename__ = "application_resumes"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_applications.id"), unique=True
    )

    # The real uploaded file, saved to disk — see app/services/file_storage.py.
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(512))

    full_name: Mapped[str] = mapped_column(String(255), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(64), default="")
    location: Mapped[str] = mapped_column(String(255), default="")
    linkedin_url: Mapped[str] = mapped_column(String(512), default="")
    portfolio_url: Mapped[str] = mapped_column(String(512), default="")
    professional_summary: Mapped[str] = mapped_column(Text, default="")

    # JSON, not child tables -- same reasoning as JobRequisition.
    # workflow_definition: nothing queries into these by individual entry
    education: Mapped[list] = mapped_column(JSON, default=list)
    experience: Mapped[list] = mapped_column(JSON, default=list)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    certifications: Mapped[list] = mapped_column(JSON, default=list)
    # [{title, content}] -- see ResumeAdditionalSection
    additional_sections: Mapped[list] = mapped_column(JSON, default=list)

    raw_extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True, default=None)
