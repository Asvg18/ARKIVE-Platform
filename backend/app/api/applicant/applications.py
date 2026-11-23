"""Applying to a job, reading one's own applications, answering an offer,
and withdrawing.
"""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infra.db import get_db
from app.infra.deps import require_role
from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus, RequisitionStatus, UserRole
from app.models.job_requisition import JobRequisition
from app.models.user import User
from app.schemas.applicant import ApplicationDetail, ApplyRequest, OfferResponseRequest
from app.services import offers
from app.services.applications import create_application_with_stage_instances

from .common import own_application
from .detail import to_detail

router = APIRouter()


# Wait before re-applying to the *same* job after an attempt ends (a team
# decision). Different jobs have no wait.
_APPLICATION_COOLDOWN_DAYS = 7

# An application in one of these states blocks a new one to the same
# job outright (including `hired`); the cooldown applies only after the
# others.
_STILL_APPLIED_STATUSES = (ApplicationStatus.active, ApplicationStatus.flagged, ApplicationStatus.hired)


@router.post("/applications", response_model=ApplicationDetail, status_code=status.HTTP_201_CREATED)
def apply_to_job(
    body: ApplyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> ApplicationDetail:
    requisition = db.get(JobRequisition, body.requisition_id)
    if (
        requisition is None
        or requisition.status != RequisitionStatus.open
        or (requisition.application_deadline is not None and requisition.application_deadline < date.today())
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")

    # No DB uniqueness on applicant+job, deliberately: a return after the
    # cooldown is a new row, so the earlier attempt's history is kept.
    most_recent_for_job = db.scalar(
        select(CandidateApplication)
        .where(
            CandidateApplication.applicant_id == user.id,
            CandidateApplication.requisition_id == requisition.id,
        )
        .order_by(CandidateApplication.created_at.desc())
        .limit(1)
    )
    if most_recent_for_job is not None:
        if most_recent_for_job.status in _STILL_APPLIED_STATUSES:
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail="You have already applied to this position."
            )
        # Only withdrawn/rejected land here. The clock starts when the
        # attempt ended (updated_at), not when it was submitted.
        cooldown_ends = most_recent_for_job.updated_at + timedelta(days=_APPLICATION_COOLDOWN_DAYS)
        if datetime.now(timezone.utc) < cooldown_ends:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    f"You can apply to this position again starting "
                    f"{cooldown_ends.strftime('%B %d, %Y')}. Only one application to the "
                    f"same job every {_APPLICATION_COOLDOWN_DAYS} days is allowed."
                ),
            )

    application = create_application_with_stage_instances(
        db, applicant_id=user.id, requisition=requisition
    )
    db.commit()
    db.refresh(application)
    return to_detail(db, application)


def _expire_overdue_offers(db: Session, applications: list[CandidateApplication]) -> None:
    """Expire any overdue offer before a read (offers are expired on read,
    not by a scheduled job; see app.services.offers). Commits only when
    something actually lapsed."""
    if any(offers.expire_offer_if_overdue(db, a) for a in applications):
        db.commit()


@router.get("/applicant/applications", response_model=list[ApplicationDetail])
def list_my_applications(
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> list[ApplicationDetail]:
    applications = db.scalars(
        select(CandidateApplication)
        .where(CandidateApplication.applicant_id == user.id)
        .order_by(CandidateApplication.id)
    ).all()
    _expire_overdue_offers(db, list(applications))
    return [to_detail(db, a) for a in applications]


@router.get("/applicant/applications/{application_id}", response_model=ApplicationDetail)
def get_my_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> ApplicationDetail:
    application = own_application(db, application_id, user)
    _expire_overdue_offers(db, [application])
    return to_detail(db, application)


@router.post("/applicant/applications/{application_id}/offer/accept", response_model=ApplicationDetail)
def accept_offer(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> ApplicationDetail:
    """Accept the offer: status stays `hired` and the onboarding checklist
    unlocks. The DFA does not move."""
    return _respond_to_offer(db, application_id, user, offers.ACCEPTED)


@router.post("/applicant/applications/{application_id}/offer/decline", response_model=ApplicationDetail)
def decline_offer(
    application_id: int,
    body: OfferResponseRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> ApplicationDetail:
    """Decline the offer: the application is withdrawn and HR is told
    (see offers.respond_to_offer). "Cancel Application" is not available
    once an offer is out, so this is the applicant's way out."""
    return _respond_to_offer(db, application_id, user, offers.DECLINED, reason=(body.reason if body else None))


def _respond_to_offer(
    db: Session,
    application_id: int,
    user: User,
    response: str,
    *,
    reason: str | None = None,
) -> ApplicationDetail:
    application = own_application(db, application_id, user)
    # an offer answered after it lapsed is not an answer: expire first
    if offers.expire_offer_if_overdue(db, application):
        db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This offer expired before your response was recorded.",
        )
    if application.status != ApplicationStatus.hired:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="There is no offer to respond to on this application.",
        )
    try:
        offers.respond_to_offer(db, application, response=response, reason=reason)
    except offers.OfferUnavailableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(application)
    return to_detail(db, application)


@router.post("/applicant/applications/{application_id}/withdraw", response_model=ApplicationDetail)
def withdraw_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.applicant)),
) -> ApplicationDetail:
    """"Cancel Application", only while the application is active. Sets
    status to `withdrawn` (distinct from HR's `rejected`), which freezes
    the DFA."""
    application = own_application(db, application_id, user)
    if application.status != ApplicationStatus.active:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Only an active application can be withdrawn."
        )
    application.status = ApplicationStatus.withdrawn
    db.commit()
    db.refresh(application)
    return to_detail(db, application)
