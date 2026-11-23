"""Job requisitions: creating one (by hand or from an uploaded job
description), reading them back, and opening or closing them.
"""

from datetime import date
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.hr.common import (
    IN_FLIGHT_STATUSES,
    PIPELINE_ROLES,
    active_candidate_count,
    application_count,
    in_flight_candidate_count,
    requisition_detail,
)
from app.domain.publish_rules import publish_blockers
from app.infra.db import get_db
from app.infra.deps import require_role
from app.infra.uploads import read_within_limit, reject_if_not_pdf
from app.models.candidate_application import CandidateApplication
from app.models.enums import RequisitionStatus
from app.models.job_requisition import JobRequisition
from app.models.user import User
from app.schemas.pipeline import (
    DuplicateJobCheck,
    JDExtractionResponse,
    RequisitionCreateRequest,
    RequisitionDetail,
    RequisitionListItem,
    RequisitionStatusUpdateRequest,
)
from app.services.jd_extraction import (
    AIExtractionFailedError,
    ExtractionNotConfiguredError,
    NotAJobDescriptionError,
    PdfTextExtractionError,
    extract_job_description,
)
from app.services.email import send_email_safely
from app.services.file_storage import save_job_description_file
from app.services.job_descriptions import (
    UnknownUploadError,
    clean_sections,
    record_initial_version,
    resolve_upload,
)
from app.services.notifications import notify
from app.services.requisition_deletion import (
    delete_requisition_cascade,
    remove_orphaned_files,
)

router = APIRouter(tags=["requisitions"])


def _refuse_incomplete(**job) -> None:
    """Publishing needs a complete job; a draft may be saved half-done. Lists
    everything still missing at once, so HR fixes it in one pass."""
    blockers = publish_blockers(**job)
    if blockers:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "publish_blocked",
                "message": "This job opening isn't ready to publish yet: " + " ".join(blockers),
                "blockers": blockers,
            },
        )


def _duplicate_message(
    db: Session, *, title: str, department: str, exclude_id: int | None = None
) -> str | None:
    """Two live (draft or open) postings with the same title in the same
    department are refused; a closed one doesn't count. Compared trimmed
    and case-insensitively.

    The refusal's wording when there is such a posting, None when not.
    Shared by the create/edit refusal and the builder's as-you-type check,
    so both say the same thing."""
    if not title.strip() or not department.strip():
        return None
    query = select(JobRequisition).where(
        func.lower(func.trim(JobRequisition.title)) == title.strip().lower(),
        func.lower(func.trim(JobRequisition.department)) == department.strip().lower(),
        JobRequisition.status.in_([RequisitionStatus.draft, RequisitionStatus.open]),
    )
    if exclude_id is not None:
        query = query.where(JobRequisition.id != exclude_id)
    existing = db.scalars(query.limit(1)).first()
    if existing is None:
        return None
    state = "a draft" if existing.status is RequisitionStatus.draft else "open"
    return (
        f'"{existing.title}" in {existing.department} already exists and is {state}. '
        "Close that one first, or use a different title or department."
    )


def _refuse_duplicate(db: Session, *, title: str, department: str, exclude_id: int | None = None) -> None:
    message = _duplicate_message(db, title=title, department=department, exclude_id=exclude_id)
    if message is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "duplicate_job", "message": message},
        )

# The two built-in workflows. Interview rounds use the generic
# interview_round_k slots (the legacy interview_hr_director/dept_head/vp
# values are never offered to new jobs); _WORKFLOW_PRESET_ROUND_LABELS
# gives them default names.
_WORKFLOW_PRESETS: dict[str, list[str]] = {
    "standard": [
        "document_upload",
        "skill_matching",
        "shortlisting",
        "examination",
        "interview_round_1",
        "interview_round_2",
        "interview_round_3",
        "final_decision",
        "onboarding",
    ],
    "streamlined": [
        "document_upload",
        # every workflow needs Shortlisting ahead of its interviews
        # (workflow_rules E5)
        "shortlisting",
        "interview_round_1",
        "interview_round_2",
        "final_decision",
        "onboarding",
    ],
}

_WORKFLOW_PRESET_ROUND_LABELS: dict[str, dict[str, str]] = {
    "standard": {
        "interview_round_1": "HR Interview",
        "interview_round_2": "Department Head Interview",
        "interview_round_3": "VP Interview",
    },
    "streamlined": {
        "interview_round_1": "HR Interview",
        "interview_round_2": "Department Head Interview",
    },
}


@router.post("/hr/requisitions/extract-jd", response_model=JDExtractionResponse)
async def extract_jd(
    job_title: str = Form(...),
    jd_file: UploadFile = File(...),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> JDExtractionResponse:
    """Returns the extracted fields and an id for the PDF they came from.
    No job is created or changed here: HR reviews/edits and then submits
    POST /hr/requisitions (or, for an existing job, the replace endpoint)
    with that id, and the version saved there keeps this exact document.

    The PDF is kept only once extraction succeeds. One HR abandons stays
    on disk unreferenced, rather than uploading the file twice."""
    reject_if_not_pdf(jd_file)

    pdf_bytes = await read_within_limit(jd_file)
    try:
        extracted = extract_job_description(job_title, pdf_bytes)
        return JDExtractionResponse(
            **extracted.model_dump(), jd_upload_id=save_job_description_file(pdf_bytes)
        )
    except NotAJobDescriptionError as exc:
        # 422, not overridable: a non-JD would become the text every match
        # score is computed against (HR can still type the job by hand)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "not_a_job_description",
                "message": (
                    f"That file looks like {exc.document_kind}, not a job description, "
                    "so nothing was extracted from it."
                ),
                "document_kind": exc.document_kind,
                "reason": exc.reason,
            },
        ) from exc
    except PdfTextExtractionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except ExtractionNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AIExtractionFailedError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


# Registered before /hr/requisitions/{requisition_id}, which would
# otherwise take "duplicate-check" as an id.
@router.get("/hr/requisitions/duplicate-check", response_model=DuplicateJobCheck)
def check_duplicate_job(
    title: str = "",
    department: str = "",
    exclude_id: int | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> DuplicateJobCheck:
    """Whether a live job already has this title in this department, so
    the builder can warn while HR types. The create and edit routes still
    refuse it themselves."""
    message = _duplicate_message(db, title=title, department=department, exclude_id=exclude_id)
    return DuplicateJobCheck(duplicate=message is not None, message=message)


@router.post(
    "/hr/requisitions",
    response_model=RequisitionDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_requisition(
    body: RequisitionCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> RequisitionDetail:
    # Checked before the job exists, so a bad document id refuses the
    # whole request with nothing written.
    try:
        upload = resolve_upload(db, body.jd_upload_id)
    except UnknownUploadError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    _refuse_duplicate(db, title=body.title, department=body.department)

    if body.workflow_definition is not None:
        workflow = [stage.value for stage in body.workflow_definition]
        round_labels = body.interview_round_labels or {}
    else:
        workflow = _WORKFLOW_PRESETS[body.workflow_preset]
        round_labels = _WORKFLOW_PRESET_ROUND_LABELS[body.workflow_preset]
    questions = [q.model_dump() for q in body.pre_screening_questions]
    if body.publish:
        _refuse_incomplete(
            application_deadline=body.application_deadline,
            workflow_definition=workflow,
            pre_screening_questions=questions,
        )

    requisition = JobRequisition(
        title=body.title,
        department=body.department,
        description=body.description,
        qualifications=body.qualifications,
        requirements=body.requirements,
        additional_sections=clean_sections(body.additional_sections),
        jd_filename=body.jd_filename,
        application_deadline=body.application_deadline,
        status=RequisitionStatus.open if body.publish else RequisitionStatus.draft,
        workflow_definition=workflow,
        interview_round_labels=round_labels,
        examination_labels=body.examination_labels or {},
        interview_durations={
            stage: minutes for stage, minutes in (body.interview_durations or {}).items() if stage in workflow
        },
        pre_screening_questions=questions,
        created_by=user.id,
    )
    db.add(requisition)
    db.flush()
    record_initial_version(db, requisition, uploaded_by=user.id, upload=upload)
    db.commit()
    db.refresh(requisition)
    return requisition_detail(db, requisition)


@router.get("/hr/requisitions/{requisition_id}", response_model=RequisitionDetail)
def get_requisition(
    requisition_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> RequisitionDetail:
    requisition = db.get(JobRequisition, requisition_id)
    if requisition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Requisition not found")
    return requisition_detail(db, requisition)


@router.get("/hr/requisitions", response_model=list[RequisitionListItem])
def list_requisitions(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> list[RequisitionListItem]:
    """Every job opening, whatever its status (/hr/dashboard/summary is
    open-only), so drafts and closed postings can be found."""
    return [
        RequisitionListItem(
            id=requisition.id,
            title=requisition.title,
            department=requisition.department,
            status=requisition.status,
            application_deadline=requisition.application_deadline,
            active_candidate_count=active_candidate_count(db, requisition.id),
            application_count=application_count(db, requisition.id),
            in_flight_candidate_count=in_flight_candidate_count(db, requisition.id),
        )
        for requisition in db.scalars(select(JobRequisition).order_by(JobRequisition.id))
    ]


@router.patch("/hr/requisitions/{requisition_id}/status", response_model=RequisitionDetail)
def update_requisition_status(
    requisition_id: int,
    body: RequisitionStatusUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> RequisitionDetail:
    """Close a posting, reopen one, or publish a draft.

    **Active candidates never block a close**: closing only stops *new*
    applications, and every existing pipeline keeps running.

    Closing also removes the job from the "other openings" suggestions
    (which rank against every open job).
    """
    requisition = db.get(JobRequisition, requisition_id)
    if requisition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Requisition not found")

    if body.status is RequisitionStatus.open:
        _refuse_duplicate(
            db, title=requisition.title, department=requisition.department, exclude_id=requisition.id
        )
        # a deadline is required to open, as at creation
        deadline = body.application_deadline or requisition.application_deadline
        if deadline is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="A job opening needs an application deadline before it can be published.",
            )
        if deadline < date.today():
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    f"That application deadline ({deadline.isoformat()}) has already passed, so the "
                    "job would be open but still hidden from applicants. Set a later one to repost it."
                ),
            )
        if requisition.status is RequisitionStatus.draft:
            _refuse_incomplete(
                application_deadline=deadline,
                workflow_definition=list(requisition.workflow_definition or []),
                pre_screening_questions=requisition.pre_screening_questions,
            )
        requisition.application_deadline = deadline

    closing = body.status is RequisitionStatus.closed and requisition.status is not RequisitionStatus.closed
    requisition.status = body.status
    recipients = _notify_job_closed(db, requisition, actor=user) if closing else []
    db.commit()
    # After the commit, so nobody is told about a close that didn't land.
    # send_email_safely never raises, so a mail problem can't undo it.
    for email, name in recipients:
        send_email_safely(
            to=email,
            subject=f"{requisition.title} is now closed.",
            body=_JOB_CLOSED_EMAIL.format(name=name, job=requisition.title),
        )
    db.refresh(requisition)
    return requisition_detail(db, requisition)


# Approved wording. Only applicants still in the process get this, and
# "is now closed" alone would read as if their application was over.
_JOB_CLOSED_EMAIL = (
    "Hi {name},\n\n"
    "The {job} opening at MSEUF has closed and is no longer accepting "
    "applications as of the moment.\n\n"
    "Your application is not affected.\n\n"
    "ARKIVE · University HR\n"
)


def _notify_job_closed(db: Session, requisition: JobRequisition, *, actor: User) -> list[tuple[str, str]]:
    """In-app notice to every applicant still in this job's pipeline
    (active or flagged); returns their (email, name) for the email that
    follows the commit."""
    rows = db.execute(
        select(CandidateApplication.id, User.id, User.email, User.full_name)
        .join(User, User.id == CandidateApplication.applicant_id)
        .where(
            CandidateApplication.requisition_id == requisition.id,
            CandidateApplication.status.in_(IN_FLIGHT_STATUSES),
        )
    ).all()
    for application_id, user_id, _email, _name in rows:
        notify(
            db,
            kind="application",
            user_id=user_id,
            actor_id=actor.id,
            application_id=application_id,
            title="Job closed",
            message=f"{requisition.title} is now closed. Your application is not affected.",
            link=f"/applicant/applications/{application_id}",
        )
    return [(email, name) for _id, _uid, email, name in rows]


@router.delete("/hr/requisitions/{requisition_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_requisition(
    requisition_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> Response:
    """Permanently removes a job opening nobody is still working through.

    **Refused (409) while anyone is `active` or `flagged`.** Past
    applications (rejected, withdrawn, hired) do not block it but are
    deleted with it; the confirmation quotes their count.

    The cascade is services/requisition_deletion. Files are unlinked only
    after the commit, so a failed transaction never deletes a file whose
    row survives.
    """
    requisition = db.get(JobRequisition, requisition_id)
    if requisition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Requisition not found")

    in_flight = in_flight_candidate_count(db, requisition_id)
    if in_flight:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f'"{requisition.title}" still has {in_flight} candidate(s) in its pipeline, so it '
                "can't be deleted. Close it instead to stop new applications while they finish, or "
                "reject or withdraw them first."
            ),
        )

    orphaned_files = delete_requisition_cascade(db, requisition)
    db.commit()
    remove_orphaned_files(orphaned_files)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
