"""Shortlisting outcomes and the acceptance a shortlisted candidate gives
before moving on.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus, StageStatus, StageType
from app.models.stage_instance import StageInstance

__all__ = [
    "ACCEPTED",
    "DECLINED",
    "ShortlistingUnavailableError",
    "open_acceptance",
    "read_acceptance",
    "rank_candidates",
    "read_outcome",
    "record_outcome",
    "respond",
]

ACCEPTED = "accepted"
DECLINED = "declined"

_ACCEPTANCE_KEY = "acceptance"
_OUTCOME_KEY = "outcome"

SHORTLISTED = "shortlisted"
NOT_SHORTLISTED = "not_shortlisted"


class ShortlistingUnavailableError(Exception):
    """There is nothing for this applicant to answer -- they were not
    shortlisted, or they have already answered. Routers turn it into a
    409."""


def shortlisting_instance(
    db: Session, application: CandidateApplication
) -> StageInstance | None:
    """This application's shortlisting StageInstance, or None for a job
    whose workflow has no shortlisting stage at all (the "streamlined"
    preset, and every job authored before the stage existed)."""
    return db.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.shortlisting,
        )
    )


def read_acceptance(db: Session, application: CandidateApplication) -> dict | None:
    """The acceptance block, or None when there is nothing to answer --
    no shortlisting stage, not shortlisted, or shortlisted before this
    feature existed."""
    instance = shortlisting_instance(db, application)
    if instance is None:
        return None
    acceptance = (instance.payload or {}).get(_ACCEPTANCE_KEY)
    return acceptance if isinstance(acceptance, dict) else None


def open_acceptance(db: Session, instance: StageInstance) -> dict:
    """Starts the wait for the candidate's answer, stored on the
    shortlisting stage's payload beside the outcome; called the moment HR
    shortlists them. Caller owns db.commit().

    Idempotent: re-recording the same outcome never erases an answer the
    candidate already gave.
    """
    payload = instance.payload or {}
    existing = payload.get(_ACCEPTANCE_KEY)
    if isinstance(existing, dict) and existing.get("response"):
        return existing

    acceptance = {
        "response": None,
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "responded_at": None,
    }
    # Reassigned rather than mutated in place -- a plain JSON column has
    # no mutation tracking, so setting a key on the nested dict would
    # never be flushed.
    instance.payload = {**payload, _ACCEPTANCE_KEY: acceptance}
    return acceptance


def clear_acceptance(db: Session, instance: StageInstance) -> None:
    """Drops the acceptance when an outcome stops being `shortlisted`.
    Leaving a stale "please confirm" on someone HR has since moved off
    the shortlist would show them a decision that is no longer theirs to
    make."""
    payload = instance.payload or {}
    if _ACCEPTANCE_KEY in payload:
        instance.payload = {k: v for k, v in payload.items() if k != _ACCEPTANCE_KEY}


def respond(db: Session, application: CandidateApplication, *, response: str) -> dict:
    """Records the candidate's answer. Caller owns db.commit(), and --
    for an acceptance -- owns advancing the stage afterwards, the same
    split every other applicant submission uses.

    Declining withdraws the application, as Cancel Application does.
    """
    instance = shortlisting_instance(db, application)
    if instance is None:
        raise ShortlistingUnavailableError("This application has no shortlisting stage.")

    payload = instance.payload or {}
    if payload.get(_OUTCOME_KEY) != SHORTLISTED:
        raise ShortlistingUnavailableError(
            "This application has not been shortlisted, so there is nothing to confirm."
        )

    acceptance = payload.get(_ACCEPTANCE_KEY)
    if not isinstance(acceptance, dict):
        raise ShortlistingUnavailableError("There is nothing to confirm on this application.")
    if acceptance.get("response"):
        raise ShortlistingUnavailableError("You have already answered this.")

    answered = {
        **acceptance,
        "response": response,
        "responded_at": datetime.now(timezone.utc).isoformat(),
    }
    instance.payload = {**payload, _ACCEPTANCE_KEY: answered}

    if response == DECLINED:
        application.status = ApplicationStatus.withdrawn
    return answered


def read_outcome(db: Session, application: CandidateApplication) -> str | None:
    """The shortlisting call already recorded for this candidate, or None
    if nobody has made one yet."""
    instance = shortlisting_instance(db, application)
    if instance is None:
        return None
    return (instance.payload or {}).get(_OUTCOME_KEY)


def rank_candidates(
    db: Session, *, requisition_id: int
) -> list[tuple[CandidateApplication, float | None, str | None]]:
    """Everyone on this job's shortlisting stage, best score first, each
    with the decision already on record if there is one. The order is
    guidance only: HR names the shortlist.

    Only active applications on the shortlisting stage. Returns
    (application, score, outcome). Candidates with no score yet sort last
    and are offered like anyone else; already-decided candidates carry
    their outcome, so the dialog starts them ticked or unticked to match.
    """
    from app.services.candidate_profile import match_score_for

    applications = db.scalars(
        select(CandidateApplication).where(
            CandidateApplication.requisition_id == requisition_id,
            CandidateApplication.current_stage == StageType.shortlisting,
            CandidateApplication.status == ApplicationStatus.active,
        )
    ).all()

    rows = [
        (application, match_score_for(db, application.id), read_outcome(db, application))
        for application in applications
    ]
    # Unscored last; id as the tiebreak so two identical scores always
    # order the same way and the list does not shuffle between renders.
    rows.sort(key=lambda r: (r[1] is None, -(r[1] or 0), r[0].id))
    return rows


def record_outcome(
    db: Session, *, instance: StageInstance, outcome: str, notes: str = ""
) -> None:
    """Writes the shortlisting call and keeps the acceptance in step with
    it: opened when shortlisted, cleared when not. Both the
    per-candidate and bulk endpoints go through here.
    """
    instance.payload = {**(instance.payload or {}), _OUTCOME_KEY: outcome, "notes": notes}
    if outcome == SHORTLISTED:
        open_acceptance(db, instance)
    else:
        clear_acceptance(db, instance)
    if instance.status == StageStatus.pending:
        instance.status = StageStatus.in_progress
