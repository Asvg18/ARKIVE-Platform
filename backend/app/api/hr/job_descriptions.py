"""Job-description history routes: listing versions, downloading their
documents, replacing and editing (rules in services/job_descriptions).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.hr.common import PIPELINE_ROLES, active_candidate_count, requisition_detail
from app.infra.db import get_db
from app.infra.deps import require_role
from app.models.job_description_version import JobDescriptionVersion
from app.models.job_requisition import JobRequisition
from app.models.user import User
from app.schemas.job_description import (
    JobDescriptionEditRequest,
    JobDescriptionReplaceRequest,
    JobDescriptionVersionDetail,
    JobDescriptionVersionRead,
)
from app.schemas.pipeline import RequisitionDetail
from app.services.file_storage import resolve_job_description_path
from app.services.job_descriptions import (
    NothingChangedError,
    UnknownUploadError,
    ensure_initial_versions,
    replace_job_description,
    scored_counts,
)

router = APIRouter(tags=["job-descriptions"])


def _read(
    version: JobDescriptionVersion,
    requisition: JobRequisition,
    uploader: User | None,
    scored: int,
) -> dict:
    return dict(
        id=version.id,
        requisition_id=requisition.id,
        job_title=requisition.title,
        department=requisition.department,
        requisition_status=requisition.status,
        version=version.version,
        is_current=version.replaced_at is None,
        original_filename=version.original_filename,
        has_file=version.stored_path is not None,
        file_size=version.file_size,
        uploaded_by_name=uploader.full_name if uploader else None,
        created_at=version.created_at,
        replaced_at=version.replaced_at,
        change_note=version.change_note,
        scored_count=scored,
    )


@router.get("/hr/job-descriptions", response_model=list[JobDescriptionVersionRead])
def list_job_descriptions(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> list[JobDescriptionVersionRead]:
    """Every version of every job's description, newest first.

    Records version 1 for any job that has none yet (an idempotent write
    inside a GET; see ensure_initial_versions)."""
    ensure_initial_versions(db)
    db.commit()

    rows = db.execute(
        select(JobDescriptionVersion, JobRequisition, User)
        .join(JobRequisition, JobRequisition.id == JobDescriptionVersion.requisition_id)
        .outerjoin(User, User.id == JobDescriptionVersion.uploaded_by)
        .order_by(JobDescriptionVersion.created_at.desc(), JobDescriptionVersion.id.desc())
    ).all()
    counts = scored_counts(db, list({requisition.id for _, requisition, _ in rows}))
    return [
        JobDescriptionVersionRead(**_read(v, r, u, counts[(r.id, v.version)])) for v, r, u in rows
    ]


def _get_version(db: Session, version_id: int) -> tuple[JobDescriptionVersion, JobRequisition]:
    version = db.get(JobDescriptionVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job description not found.")
    requisition = db.get(JobRequisition, version.requisition_id)
    return version, requisition


@router.get("/hr/job-descriptions/{version_id}", response_model=JobDescriptionVersionDetail)
def get_job_description(
    version_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> JobDescriptionVersionDetail:
    """One version with its text -- what anyone scored against it was
    actually measured against, even after it has been replaced."""
    version, requisition = _get_version(db, version_id)
    uploader = db.get(User, version.uploaded_by) if version.uploaded_by else None
    scored = scored_counts(db, [requisition.id])[(requisition.id, version.version)]
    return JobDescriptionVersionDetail(
        **_read(version, requisition, uploader, scored),
        description=version.description,
        qualifications=version.qualifications,
        requirements=version.requirements,
        additional_sections=version.additional_sections or [],
    )


@router.get("/hr/job-descriptions/{version_id}/file")
def download_job_description_file(
    version_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> FileResponse:
    version, _ = _get_version(db, version_id)
    if version.stored_path is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="No document was kept for this version. It was typed by hand, or added before documents were saved.",
        )
    path = resolve_job_description_path(version.stored_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="The document file is missing.")
    return FileResponse(
        path, media_type="application/pdf", filename=version.original_filename or "job-description.pdf"
    )


@router.post(
    "/hr/requisitions/{requisition_id}/job-description",
    response_model=JobDescriptionVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def replace_requisition_job_description(
    requisition_id: int,
    body: JobDescriptionReplaceRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> JobDescriptionVersionRead:
    """Puts a new job description in force for this job.

    Applicants already scored keep their scores (no one is re-scored).
    Refused unless `confirm_title` matches the job's title, since this
    text is the basis of every future match score."""
    requisition = db.get(JobRequisition, requisition_id)
    if requisition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Requisition not found")

    if body.confirm_title.strip().casefold() != requisition.title.strip().casefold():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f'Type the job title exactly ("{requisition.title}") to confirm the replacement.',
        )

    try:
        version = replace_job_description(
            db,
            requisition,
            replaced_by=user.id,
            description=body.description,
            qualifications=body.qualifications,
            requirements=body.requirements,
            additional_sections=body.additional_sections,
            upload_id=body.jd_upload_id,
            original_filename=body.jd_filename,
            change_note=body.change_note,
        )
    except NothingChangedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except UnknownUploadError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    db.commit()
    db.refresh(version)
    scored = scored_counts(db, [requisition.id])[(requisition.id, version.version)]
    return JobDescriptionVersionRead(**_read(version, requisition, user, scored))


@router.patch("/hr/requisitions/{requisition_id}/job-description", response_model=RequisitionDetail)
def edit_requisition_job_description(
    requisition_id: int,
    body: JobDescriptionEditRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> RequisitionDetail:
    """Edits the job description from the job opening's own page.

    Locked while the job has an active candidate, like the stage order.
    Otherwise a replacement like any other (a new version, the cached
    embedding cleared, nobody re-scored), without the typed-title
    confirmation."""
    requisition = db.get(JobRequisition, requisition_id)
    if requisition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Requisition not found")

    if active_candidate_count(db, requisition.id) > 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This job's description can't be edited while it has active candidates.",
        )

    if not any((text or "").strip() for text in (body.description, body.qualifications, body.requirements)):
        # the AI match reads these three fields; with all of them empty
        # it would score every applicant against the title alone. The
        # additional sections don't count -- the match never reads them.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A job description needs a role description, qualifications or requirements filled in.",
        )

    try:
        replace_job_description(
            db,
            requisition,
            replaced_by=user.id,
            description=body.description,
            qualifications=body.qualifications,
            requirements=body.requirements,
            additional_sections=body.additional_sections,
            upload_id=None,
            original_filename=None,
            change_note=body.change_note,
        )
    except NothingChangedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    db.commit()
    db.refresh(requisition)
    return requisition_detail(db, requisition)
