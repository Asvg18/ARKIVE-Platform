"""Shared lookup for an application's supplemental documents -- used by
both the applicant's own view and the HR Candidate Profile, same role
resume_profile.py plays for the one required resume."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application_document import ApplicationDocument


def list_application_documents(db: Session, application_id: int) -> list[ApplicationDocument]:
    return list(
        db.scalars(
            select(ApplicationDocument)
            .where(ApplicationDocument.application_id == application_id)
            .order_by(ApplicationDocument.created_at)
        )
    )
