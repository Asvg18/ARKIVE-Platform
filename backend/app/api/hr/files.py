"""Downloads of the files attached to an application -- the resume and
any supplemental documents.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.hr.common import PIPELINE_ROLES
from app.infra.db import get_db
from app.infra.deps import require_role
from app.models.application_document import ApplicationDocument
from app.models.candidate_application import CandidateApplication
from app.models.user import User
from app.services.file_storage import resolve_document_path, resolve_resume_path
from app.services.resume_profile import get_application_resume

router = APIRouter(tags=["files"])


@router.get("/hr/applications/{application_id}/resume-file")
def download_candidate_resume_file(
    application_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> FileResponse:
    """Lets HR open the candidate's real uploaded resume — not just the
    AI-extracted fields — to verify the extraction against the source."""
    application = db.get(CandidateApplication, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found")
    resume = get_application_resume(db, application.id)
    if resume is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No resume uploaded yet.")
    path = resolve_resume_path(resume.stored_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resume file is missing.")
    return FileResponse(path, media_type="application/pdf", filename=resume.original_filename)


@router.get("/hr/applications/{application_id}/documents/{document_id}/file")
def download_candidate_supplemental_document_file(
    application_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> FileResponse:
    """Mirrors download_candidate_resume_file above, for the
    supplemental files instead of the single resume."""
    document = db.get(ApplicationDocument, document_id)
    if document is None or document.application_id != application_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found.")
    path = resolve_document_path(document.stored_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document file is missing.")
    return FileResponse(path, media_type="application/pdf", filename=document.original_filename)
