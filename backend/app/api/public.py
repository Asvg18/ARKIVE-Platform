"""Unauthenticated job-listing routes -- the homepage and job detail
modal read from here before an applicant ever logs in."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.infra.db import get_db
from app.models.enums import RequisitionStatus
from app.models.job_requisition import JobRequisition
from app.schemas.public import JobDetail, JobListItem, JobListResponse
from app.services.stage_labels import resolve_stage_label

router = APIRouter(prefix="/public", tags=["public"])

# without this, ?limit=100000 lets an unauthenticated caller ask the
# server to materialize the whole table in one request
MAX_PAGE_SIZE = 100


def _not_past_deadline():
    return or_(JobRequisition.application_deadline.is_(None), JobRequisition.application_deadline >= date.today())


def _open_jobs():
    """Every job the public is allowed to see, before any user filters."""
    return select(JobRequisition).where(
        JobRequisition.status == RequisitionStatus.open, _not_past_deadline()
    )


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, max_length=200, description="Free-text search"),
    department: Annotated[list[str] | None, Query()] = None,
    limit: int = Query(default=MAX_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> JobListResponse:
    """Public job board, filtered server-side.

    `q` also searches qualifications and requirements, so a skill
    ("CCNA") finds the posting that asks for it.
    """
    statement = _open_jobs()

    if q and q.strip():
        # Escape the LIKE wildcards so a literal "100%" searches for that
        # string instead of matching everything.
        term = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{term}%"
        statement = statement.where(
            or_(
                JobRequisition.title.ilike(pattern),
                JobRequisition.department.ilike(pattern),
                JobRequisition.description.ilike(pattern),
                JobRequisition.qualifications.ilike(pattern),
                JobRequisition.requirements.ilike(pattern),
            )
        )

    if department:
        statement = statement.where(JobRequisition.department.in_(department))

    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0

    jobs = db.scalars(statement.order_by(JobRequisition.id).limit(limit).offset(offset)).all()

    departments = db.scalars(
        _open_jobs().with_only_columns(JobRequisition.department).distinct().order_by(JobRequisition.department)
    ).all()

    return JobListResponse(
        items=[
            JobListItem(
                id=job.id,
                title=job.title,
                department=job.department,
                description=job.description,
                qualifications=job.qualifications,
                requirements=job.requirements,
                additional_sections=job.additional_sections or [],
                application_deadline=job.application_deadline,
                stage_count=len(job.workflow_definition),
                created_at=job.created_at,
            )
            for job in jobs
        ],
        total=total,
        departments=list(departments),
    )


@router.get("/jobs/{job_id}", response_model=JobDetail)
def get_job(job_id: int, db: Session = Depends(get_db)) -> JobDetail:
    job = db.get(JobRequisition, job_id)
    if (
        job is None
        or job.status != RequisitionStatus.open
        or (job.application_deadline is not None and job.application_deadline < date.today())
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
    detail = JobDetail.model_validate(job)
    detail.stage_labels = [resolve_stage_label(stage, job) for stage in job.workflow_definition]
    return detail
