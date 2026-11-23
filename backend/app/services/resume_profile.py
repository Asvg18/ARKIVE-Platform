"""Shared lookup/shaping for the persisted ApplicationResume row -- used
by the applicant's view, the HR Candidate Profile, and the Evaluator's
interview detail, so the three don't each reimplement the same query."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application_resume import ApplicationResume
from app.schemas.resume import ApplicationResumeRead


def get_application_resume(db: Session, application_id: int) -> ApplicationResume | None:
    return db.scalar(
        select(ApplicationResume).where(ApplicationResume.application_id == application_id)
    )


def to_resume_read(resume: ApplicationResume | None) -> ApplicationResumeRead | None:
    if resume is None:
        return None
    return ApplicationResumeRead.model_validate(resume, from_attributes=True)
