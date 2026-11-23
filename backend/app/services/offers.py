"""The offer an accepted applicant has to answer, and the clock it runs
on.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus, StageStatus, StageType, UserRole
from app.models.job_requisition import JobRequisition
from app.models.stage_instance import StageInstance
from app.models.user import User
from app.services.notifications import notify

# constant, not a per-job column -- nobody's asked for per-requisition
# configurability, and a column added "just in case" is a migration +
# form field + validation rule to carry forever
OFFER_RESPONSE_WINDOW_DAYS = 7

ACCEPTED = "accepted"
DECLINED = "declined"
# written by expiry, never by the applicant -- closing unanswered is a
# different fact from declining, and reads differently to HR
EXPIRED = "expired"

_OFFER_KEY = "offer"


def final_decision_instance(
    db: Session, application: CandidateApplication, *, create: bool = False
) -> StageInstance | None:
    """The final_decision StageInstance -- where both the decision record
    and the offer get written.

    `create` adds the row when missing (an older application, or a
    workflow without a final_decision stage)."""
    instance = db.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.final_decision,
        )
    )
    if instance is None and create:
        instance = StageInstance(
            application_id=application.id,
            stage_type=StageType.final_decision,
            status=StageStatus.pending,
        )
        db.add(instance)
    return instance


def read_offer(db: Session, application: CandidateApplication) -> dict | None:
    """The offer block on the final_decision payload (beside the decision
    record), or None if there never was one (never hired, or hired with
    no deadline, which therefore never expires)."""
    instance = final_decision_instance(db, application)
    if instance is None:
        return None
    offer = (instance.payload or {}).get(_OFFER_KEY)
    return offer if isinstance(offer, dict) and offer.get("deadline") else None


def _write_offer(db: Session, application: CandidateApplication, offer: dict | None) -> None:
    """Reassigned, not mutated in place -- a plain JSON column has no
    mutation tracking, so setting a key on the nested dict in place would
    never get flushed. Same spread-and-replace convention as every other
    payload write."""
    instance = final_decision_instance(db, application, create=True)
    payload = instance.payload or {}
    if offer is None:
        instance.payload = {k: v for k, v in payload.items() if k != _OFFER_KEY}
    else:
        instance.payload = {**payload, _OFFER_KEY: offer}


def open_offer(
    db: Session,
    application: CandidateApplication,
    *,
    window_days: int = OFFER_RESPONSE_WINDOW_DAYS,
) -> dict:
    """Starts the response window, called the moment HR hires: the
    applicant then accepts or declines by the deadline. Caller owns
    db.commit()."""
    now = datetime.now(timezone.utc)
    offer = {
        "deadline": (now + timedelta(days=window_days)).isoformat(),
        "window_days": window_days,
        "opened_at": now.isoformat(),
        "response": None,
        "responded_at": None,
    }
    _write_offer(db, application, offer)
    return offer


def clear_offer(db: Session, application: CandidateApplication) -> None:
    """Called when the application stops being accepted for some other
    reason (HR reopens it, rejects after the fact) -- leaving a stale
    window behind would let expire_offer_if_overdue withdraw an
    application that's not even on offer anymore."""
    _write_offer(db, application, None)


def respond_to_offer(
    db: Session,
    application: CandidateApplication,
    *,
    response: str,
    reason: str | None = None,
) -> dict:
    """Records the applicant's answer. Declining also withdraws the
    application, as Cancel Application does. Caller owns db.commit()."""
    offer = read_offer(db, application)
    if offer is None:
        raise OfferUnavailableError("There is no offer to respond to on this application.")
    if offer.get("response"):
        raise OfferUnavailableError("This offer has already been answered.")

    answered = {
        **offer,
        "response": response,
        "responded_at": datetime.now(timezone.utc).isoformat(),
        "reason": (reason or "").strip() or None,
    }
    _write_offer(db, application, answered)

    if response == DECLINED:
        application.status = ApplicationStatus.withdrawn
        _notify_hr(
            db, application, title="Offer declined", detail="declined the offer", actor_id=application.applicant_id
        )
    return answered


def is_overdue(offer: dict | None, *, now: datetime | None = None) -> bool:
    """True when an unanswered offer's window has closed."""
    if not offer or offer.get("response"):
        return False
    deadline = offer.get("deadline")
    if not deadline:
        return False
    return _parse(deadline) <= (now or datetime.now(timezone.utc))


def expire_offer_if_overdue(db: Session, application: CandidateApplication) -> bool:
    """Expires the offer if overdue; True when this call expired it
    (uncommitted). Called on every read instead of by a scheduled job, so
    an unread overdue offer is withdrawn the next time anyone looks. Only
    a `hired` application with an unanswered deadline can expire; one
    with no deadline never does.

    Caller owns db.commit(); read-only routes commit only on True."""
    if application.status != ApplicationStatus.hired:
        return False
    offer = read_offer(db, application)
    if not is_overdue(offer):
        return False

    _write_offer(
        db,
        application,
        {
            **offer,
            "response": EXPIRED,
            "responded_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    application.status = ApplicationStatus.withdrawn
    # Nobody did this: the clock ran out, so it comes from ARKIVE.
    _notify_hr(
        db,
        application,
        title="Offer lapsed",
        actor_id=None,
        detail=(
            f"did not respond within {offer.get('window_days', OFFER_RESPONSE_WINDOW_DAYS)} days, so "
            "the offer has lapsed and the application is now withdrawn"
        ),
    )
    return True


class OfferUnavailableError(Exception):
    """Raised when there is nothing to answer — no offer, or one that has
    already been answered. Routers translate it to a 409."""


def _notify_hr(
    db: Session, application: CandidateApplication, *, title: str, detail: str, actor_id: int | None
) -> None:
    """Notifies every HR admin instead of tracking a single "owner" per
    job -- simpler and more robust for a small team where any admin might
    act on it. Same choice as the reschedule notification in
    app.api.evaluator."""
    applicant = db.get(User, application.applicant_id)
    requisition = db.get(JobRequisition, application.requisition_id)
    applicant_name = applicant.full_name if applicant else f"Applicant {application.applicant_id}"
    job_title = requisition.title if requisition else "this position"
    for hr_admin in db.scalars(select(User).where(User.role == UserRole.hr_admin)):
        notify(
            db,
            kind="decision",
            user_id=hr_admin.id,
            actor_id=actor_id,
            application_id=application.id,
            title=title,
            message=f"{applicant_name} {detail} for {job_title}.",
            link=f"/hr/applications/{application.id}",
        )


def _parse(value: str) -> datetime:
    """Tolerant of a naive stored timestamp -- open_offer always writes
    tz-aware, but a hand-edited or seeded payload might not be, and
    comparing naive to aware raises."""
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
