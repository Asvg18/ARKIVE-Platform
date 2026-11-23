"""The resume (reading it, submitting it at Document Upload, downloading it)
and supplemental documents.
"""

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infra.db import get_db
from app.infra.deps import require_role
from app.infra.uploads import read_within_limit, reject_if_not_pdf
from app.models.application_document import ApplicationDocument
from app.models.application_resume import ApplicationResume
from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus, StageType, UserRole
from app.models.job_requisition import JobRequisition
from app.models.stage_instance import StageInstance
from app.models.user import User
from app.schemas.applicant import ApplicationDetail
from app.schemas.resume import ResumeExtractionResult
from app.services.agents import DOCUMENT_PARSING
from app.services.file_storage import (
    resolve_document_path,
    resolve_resume_path,
    save_resume_file,
    save_supplemental_document_file,
)
from app.services.pdf_text import PdfTextExtractionError
from app.services.resume_extraction import (
    AIExtractionFailedError,
    ExtractionNotConfiguredError,
    extract_resume,
)
from app.services.resume_profile import get_application_resume
from app.services.resume_text import read_resume_text

from .common import advance, own_application, require_current_stage
from .detail import to_detail

logger = logging.getLogger(__name__)

router = APIRouter()

# a sanity cap on stored resume text; larger than what is sent to the AI
# (resume_extraction._MAX_SOURCE_CHARS), since storage is not per-call
_RAW_TEXT_STORAGE_MAX_CHARS = 50_000


@router.post("/applicant/resume/extract", response_model=ResumeExtractionResult)
async def extract_resume_preview(
    resume_file: UploadFile = File(...),
    _user: User = Depends(require_role(UserRole.applicant)),
) -> ResumeExtractionResult:
    """Returns the standardized fields only; nothing is persisted here.
    The applicant reviews/edits the result, then POST .../document-upload
    submits the (possibly-edited) fields together with the file itself."""
    reject_if_not_pdf(resume_file)
    pdf_bytes = await read_within_limit(resume_file)
    try:
        # a blocking OpenAI call inside an async route stalls the whole
        # event loop -- every other user's request waits behind it
        return await run_in_threadpool(extract_resume, pdf_bytes)
    except PdfTextExtractionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except ExtractionNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AIExtractionFailedError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


def _score_resume_against_job(
    db: Session, *, application: CandidateApplication, requisition: JobRequisition
) -> None:
    """Score the resume against the job as soon as it is uploaded, onto the
    skill_matching stage's payload (while that stage is still `pending`).

    Flagging is not decided here: a weak score freezes the application at
    skill_matching only after pre-screening (see submit_pre_screening).

    Never raises: a missing or failing model must not cost the applicant
    their upload. Pre-screening scores it instead when nothing was stored.
    """
    instance = db.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.skill_matching,
        )
    )
    # A job whose workflow skips AI Pre-Screening entirely (the
    # "streamlined" preset) has nowhere to put this and nothing to do.
    if instance is None:
        return

    resume = get_application_resume(db, application.id)
    if resume is None:
        return

    from app.services.skill_matching import run_skill_matching

    try:
        match = run_skill_matching(db, resume=resume, target_requisition=requisition)
    except (ExtractionNotConfiguredError, AIExtractionFailedError):
        logger.info(
            "Skill matching unavailable at resume upload for application %s; "
            "it will run at pre-screening instead.",
            application.id,
        )
        return
    except Exception:
        logger.exception(
            "Skill matching failed at resume upload for application %s; "
            "it will run at pre-screening instead.",
            application.id,
        )
        return

    instance.payload = {**(instance.payload or {}), **match.model_dump()}


@router.post(
    "/applicant/applications/{application_id}/document-upload", response_model=ApplicationDetail
)
async def submit_document_upload(
    application_id: int,
    resume_file: UploadFile = File(...),
    resume_data: str = Form(...),
    letter_of_intent: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> ApplicationDetail:
    """Saves the resume (file + reviewed fields) as the application's
    ApplicationResume row, then advances document_upload. resume_data is
    the reviewed ResumeExtractionResult as a JSON string (this is a
    multipart request).

    Only reading the upload happens on the event loop; all database and
    OpenAI work runs in one worker thread. Splitting them can deadlock the
    server when a duplicate submit waits on the first one's uncommitted
    row."""
    reject_if_not_pdf(resume_file)
    try:
        parsed_resume = ResumeExtractionResult.model_validate_json(resume_data)
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid resume data."
        ) from exc

    pdf_bytes = await read_within_limit(resume_file)
    return await run_in_threadpool(
        _persist_resume_and_advance,
        db,
        user=user,
        application_id=application_id,
        pdf_bytes=pdf_bytes,
        original_filename=resume_file.filename or "resume.pdf",
        parsed_resume=parsed_resume,
        letter_of_intent=letter_of_intent,
    )


def _persist_resume_and_advance(
    db: Session,
    *,
    user: User,
    application_id: int,
    pdf_bytes: bytes,
    original_filename: str,
    parsed_resume: ResumeExtractionResult,
    letter_of_intent: str | None,
) -> ApplicationDetail:
    # row-locked: a duplicate submit waits for the first to commit, then
    # gets a clean 409 instead of inserting a second resume
    application = db.scalar(
        select(CandidateApplication)
        .where(
            CandidateApplication.id == application_id,
            CandidateApplication.applicant_id == user.id,
        )
        .with_for_update()
    )
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found")
    require_current_stage(application, StageType.document_upload)

    # a scanned file the preview already read is reused
    # (services/resume_text.py); any other file is checked and read here
    try:
        raw_text = read_resume_text(pdf_bytes, max_chars=_RAW_TEXT_STORAGE_MAX_CHARS)
    except PdfTextExtractionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except ExtractionNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AIExtractionFailedError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    stored_path = save_resume_file(pdf_bytes)
    db.add(
        ApplicationResume(
            application_id=application.id,
            original_filename=original_filename,
            stored_path=stored_path,
            full_name=parsed_resume.full_name,
            email=parsed_resume.email,
            phone=parsed_resume.phone,
            location=parsed_resume.location,
            linkedin_url=parsed_resume.linkedin_url,
            portfolio_url=parsed_resume.portfolio_url,
            professional_summary=parsed_resume.professional_summary,
            education=[e.model_dump() for e in parsed_resume.education],
            experience=[e.model_dump() for e in parsed_resume.experience],
            skills=parsed_resume.skills,
            certifications=parsed_resume.certifications,
            additional_sections=[s.model_dump() for s in parsed_resume.additional_sections],
            raw_extracted_text=raw_text,
        )
    )
    # flushed, not just added: the sufficiency gate below SELECTs the
    # resume, and with autoflush off a pending add would be invisible
    db.flush()

    # logged here, where there is an application to attribute it to.
    # counts and field names only: the log is an audit trail, not a copy
    # of the resume
    DOCUMENT_PARSING.log(
        db,
        application_id=application.id,
        triggered_by_stage=StageType.document_upload.value,
        output={
            "original_filename": original_filename,
            "skills_extracted": len(parsed_resume.skills),
            "experience_entries": len(parsed_resume.experience),
            "education_entries": len(parsed_resume.education),
            "certifications_extracted": len(parsed_resume.certifications),
            "additional_sections": [s.title for s in parsed_resume.additional_sections],
            "raw_text_chars": len(raw_text),
        },
    )

    requisition = db.get(JobRequisition, application.requisition_id)
    _score_resume_against_job(db, application=application, requisition=requisition)
    return advance(db, application, requisition, {"letter_of_intent": letter_of_intent})


@router.get("/applicant/applications/{application_id}/resume-file")
def download_my_resume_file(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> FileResponse:
    application = own_application(db, application_id, user)
    resume = get_application_resume(db, application.id)
    if resume is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No resume uploaded yet.")
    path = resolve_resume_path(resume.stored_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resume file is missing.")
    return FileResponse(path, media_type="application/pdf", filename=resume.original_filename)


@router.post("/applicant/applications/{application_id}/documents", response_model=ApplicationDetail)
async def upload_supplemental_document(
    application_id: int,
    file: UploadFile = File(...),
    label: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> ApplicationDetail:
    """Attach a supplemental file (reference letter, portfolio, ...) any
    time after document upload. Separate from the one required resume."""
    application = own_application(db, application_id, user)
    if application.status != ApplicationStatus.active:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Documents can only be added to an active application."
        )
    if not label.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail='A label is required (e.g. "Reference Letter").',
        )
    reject_if_not_pdf(file)
    pdf_bytes = await read_within_limit(file)
    stored_path = save_supplemental_document_file(pdf_bytes)
    db.add(
        ApplicationDocument(
            application_id=application.id,
            label=label.strip(),
            original_filename=file.filename or "document.pdf",
            stored_path=stored_path,
        )
    )
    db.commit()
    db.refresh(application)
    return to_detail(db, application)


@router.get("/applicant/applications/{application_id}/documents/{document_id}/file")
def download_my_supplemental_document_file(
    application_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> FileResponse:
    application = own_application(db, application_id, user)
    document = db.get(ApplicationDocument, document_id)
    if document is None or document.application_id != application.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found.")
    path = resolve_document_path(document.stored_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document file is missing.")
    return FileResponse(path, media_type="application/pdf", filename=document.original_filename)
