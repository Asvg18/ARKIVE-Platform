from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base
from app.models.mixins import TimestampMixin


class ApplicationDocument(Base, TimestampMixin):
    """A supplemental document (reference letter, updated portfolio, etc.)
    the applicant adds after their initial document_upload submission --
    distinct from the single required ApplicationResume, an application
    can have any number of these. TimestampMixin's created_at doubles as
    "uploaded_at"."""

    __tablename__ = "application_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("candidate_applications.id"))

    label: Mapped[str] = mapped_column(String(255))

    # The real uploaded file, saved to disk — see
    # app/services/file_storage.py's save_supplemental_document_file.
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(512))
