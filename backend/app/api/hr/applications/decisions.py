"""HR's decisions that write to the candidate: hiring or rejecting
(with its record and letters), and the whole-job shortlist.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.hr.common import PIPELINE_ROLES
from app.domain.dfa import build_transition_table
from app.infra.db import get_db
from app.infra.deps import require_role
from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus, StageStatus, StageType
from app.models.job_requisition import JobRequisition
from app.models.stage_instance import StageInstance
from app.models.user import User
from app.schemas.pipeline import (
    ApplicationListItem,
    ShortlistedCandidate,
    ShortlistRequest,
    ShortlistResult,
    StatusUpdateRequest,
)
from app.schemas.user import avatar_url
from app.services import offers
from app.services.applications import transition_application_stage
from app.services import exam_scheduling, shortlisting
from app.services.email import send_email_safely
from app.services.candidate_profile import build_candidate_profile, match_score_for
from app.services.hire_decision import build_decision_readiness, build_decision_record
from app.services.notifications import notify
from app.services.stage_labels import resolve_stage_label

router = APIRouter()


# (title, message) -- the rejection's title stays as neutral as the
# shortlist's "not this time" one, since it is the line seen first.
_DECISION_NOTIFICATIONS: dict[str, tuple[str, str]] = {
    "hired": ("You've been selected", "Congratulations, you've been selected for {job}."),
    "rejected": (
        "An update on your application",
        "Thank you for your interest in {job}. We've decided not to move forward with your application.",
    ),
    "active": ("Application reopened", "Your application for {job} has been reopened."),
}


#: The final decision by email as well as in the app. The hire email
#: states no salary, start date or conditions (ARKIVE has none of them).
#: No `withdrawn` email: the candidate made that decision themselves.
_DECISION_EMAILS: dict[str, tuple[str, str]] = {
    "hired": (
        "You've been selected: {job}",
        "Hi {name},\n\n"
        "Congratulations. Following the selection process, you have been chosen "
        "for {job} at Manuel S. Enverga University Foundation.\n\n"
        "A formal offer is waiting on your application page, together with the "
        "date your response is due. Please sign in to review and respond to it. "
        "The offer lapses if it is not answered in time.\n\n"
        "We look forward to working with you.\n"
    ),
    "rejected": (
        "Update on your application: {job}",
        "Hi {name},\n\n"
        "Thank you for your interest in {job} at Manuel S. Enverga University "
        "Foundation, and for the time you gave to the selection process.\n\n"
        "After careful consideration we have decided not to move forward with "
        "your application for this position. This reflects the fit for this "
        "particular role and the strength of the field; it is not a judgement "
        "on your abilities.\n\n"
        "We would genuinely welcome an application from you for future "
        "openings.\n"
    ),
    "active": (
        "Your application has been reopened: {job}",
        "Hi {name},\n\n"
        "Your application for {job} has been reopened and is active again. You "
        "can follow its progress on your application page.\n"
    ),
}


def _record_decision(
    db: Session,
    *,
    application: CandidateApplication,
    record: dict,
) -> None:
    """Appends the decision to the final_decision stage's payload.

    A **list**, so reopening and deciding again keeps the earlier
    record; the last entry is the effective decision. Creates the stage
    row if missing (an older application, or a workflow without a
    final_decision stage)."""
    instance = offers.final_decision_instance(db, application, create=True)

    payload = instance.payload or {}
    # reassigned, not mutated: a plain JSON column has no mutation
    # tracking, so .append() would never be saved
    instance.payload = {**payload, "decisions": [*payload.get("decisions", []), record]}


@router.patch("/hr/applications/{application_id}/status", response_model=ApplicationListItem)
def update_application_status(
    application_id: int,
    body: StatusUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> ApplicationListItem:
    """Closes (or reopens) an application and records the decision.
    Status is deliberately **not** coupled to the DFA.

    Only `hired` is gated: an incomplete record is refused unless
    `acknowledged_incomplete` is sent with a reason, and that
    acknowledgement goes into the record."""
    application = db.get(CandidateApplication, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found")

    requisition = db.get(JobRequisition, application.requisition_id)
    applicant = db.get(User, application.applicant_id)

    previous_status = application.status
    if body.status != previous_status:
        # built once, before the change, for the gate, record and snapshot
        profile = build_candidate_profile(db, application_id)
        readiness = build_decision_readiness(profile, requisition)

        if body.status == ApplicationStatus.hired and not readiness.is_complete:
            if not body.acknowledged_incomplete:
                # structured, so the client shows the server's own list
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail={
                        "code": "incomplete_record",
                        "message": readiness.summary,
                        "blockers": [blocker.model_dump() for blocker in readiness.blockers],
                    },
                )
            if not (body.reason or "").strip():
                # overriding the gate requires a reason
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail={
                        "code": "reason_required",
                        "message": (
                            "Approving an incomplete record needs a reason on file."
                        ),
                        "blockers": [blocker.model_dump() for blocker in readiness.blockers],
                    },
                )

        application.status = body.status
        # a reopened application's old exam seat holds again -- one whose
        # session filled up meanwhile is given back, so the session isn't
        # oversold (exam_scheduling.reconcile_reopened)
        if body.status == ApplicationStatus.active and previous_status in (
            ApplicationStatus.rejected,
            ApplicationStatus.withdrawn,
        ):
            exam_scheduling.reconcile_reopened(db, application)
        # the offer clock exists only while hired; a stale one would let
        # the expiry check withdraw someone not on offer
        if body.status == ApplicationStatus.hired:
            offers.open_offer(db, application)
        elif previous_status == ApplicationStatus.hired:
            offers.clear_offer(db, application)
        _record_decision(
            db,
            application=application,
            record=build_decision_record(
                profile=profile,
                readiness=readiness,
                body=body,
                actor=user,
                previous_status=previous_status,
            ),
        )
        # Approve Hire at Final Decision also moves the candidate onto
        # Onboarding, where the applicant's checklist lives; there is no
        # separate "Advance to Onboarding" step. The decision recorded
        # just above is what final_decision needs before it can be left.
        if (
            body.status == ApplicationStatus.hired
            and application.current_stage == StageType.final_decision
            and build_transition_table(requisition.workflow_definition).get(StageType.final_decision.value)
            == StageType.onboarding.value
        ):
            transition_application_stage(
                db,
                application=application,
                requisition=requisition,
                target_stage=StageType.onboarding,
                triggered_by=str(user.id),
            )
        decision_notice = _DECISION_NOTIFICATIONS.get(body.status.value)
        if decision_notice:
            title, message = decision_notice
            notify(
                db,
                kind="decision",
                user_id=application.applicant_id,
                actor_id=user.id,
                application_id=application.id,
                title=title,
                message=message.format(job=requisition.title),
                link=f"/applicant/applications/{application.id}",
            )
            # `applicant` is already loaded further up, for the response
            # body. send_email_safely swallows its own failures, so a mail
            # problem can never turn a recorded hire into a 500.
            decision_email = _DECISION_EMAILS.get(body.status.value)
            if decision_email is not None:
                subject, template = decision_email
                send_email_safely(
                    to=applicant.email,
                    subject=subject.format(job=requisition.title),
                    body=template.format(name=applicant.full_name, job=requisition.title),
                )
        db.commit()
        db.refresh(application)

    next_stage = None
    if application.current_stage is not None:
        next_stage = build_transition_table(requisition.workflow_definition).get(
            application.current_stage.value
        )
    return ApplicationListItem(
        id=application.id,
        applicant_name=applicant.full_name,
        applicant_avatar_url=avatar_url(applicant.avatar_file),
        job_title=requisition.title,
        requisition_id=requisition.id,
        current_stage=application.current_stage,
        current_stage_label=resolve_stage_label(
            application.current_stage.value if application.current_stage else None, requisition
        ),
        next_stage=next_stage,
        status=application.status,
        match_score=match_score_for(db, application.id),
    )


def _greeting(name: str, letter: str) -> str:
    """HR's letter, verbatim, under a greeting with the person's name."""
    return f"Hi {name},\n\n{letter.strip()}\n"


@router.post(
    "/hr/requisitions/{requisition_id}/shortlist",
    response_model=ShortlistResult,
)
def shortlist_candidates(
    requisition_id: int,
    body: ShortlistRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> ShortlistResult:
    """Records HR's shortlist for a whole job at once and writes to
    everyone on both sides of it.

    **HR names the shortlist** by application id; the match score is
    guidance only, and nothing is picked for HR.

    A decision already recorded on a candidate's profile is final here:
    not changed or written to, and returned in `already_decided`.
    Everyone else not named is recorded as not shortlisted.

    Email failures are counted, never raised, so a mail outage cannot
    leave the shortlist half recorded.
    """
    requisition = db.get(JobRequisition, requisition_id)
    if requisition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Requisition not found")
    if StageType.shortlisting.value not in requisition.workflow_definition:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This job's workflow has no Shortlisting stage.",
        )

    field = shortlisting.rank_candidates(db, requisition_id=requisition_id)
    pool = [(a, score) for a, score, outcome in field if not outcome]
    decided = [(a, outcome) for a, _, outcome in field if outcome]

    if not pool:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                "Every candidate on this job's shortlisting stage already has a decision "
                "recorded. Change one on that candidate's profile."
                if decided
                else "No candidates are waiting on a shortlisting decision for this job."
            ),
        )

    pool_ids = {application.id for application, _ in pool}
    chosen = set(body.shortlisted_application_ids)
    # an id outside the undecided pool is refused, not ignored
    if chosen - pool_ids:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                "Some of those candidates already have a shortlisting decision recorded, or have "
                "moved on. Reopen this dialog to see who is still waiting."
            ),
        )

    # each letter is required only if it has somebody to go to
    if chosen and not body.shortlisted_letter.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Write the message for the candidates you shortlisted before sending.",
        )
    if len(chosen) < len(pool) and not body.not_shortlisted_letter.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Write the message for the candidates you did not shortlist before sending.",
        )

    shortlisted_rows: list[ShortlistedCandidate] = []
    not_shortlisted_rows: list[ShortlistedCandidate] = []
    failures = 0

    for position, (application, score) in enumerate(pool, start=1):
        made_the_cut = application.id in chosen
        outcome = shortlisting.SHORTLISTED if made_the_cut else shortlisting.NOT_SHORTLISTED

        instance = shortlisting.shortlisting_instance(db, application)
        if instance is None:
            # an application older than the stage still gets an answer:
            # create its row
            instance = StageInstance(
                application_id=application.id,
                stage_type=StageType.shortlisting,
                status=StageStatus.in_progress,
            )
            db.add(instance)
            db.flush()

        shortlisting.record_outcome(db, instance=instance, outcome=outcome)

        applicant = db.get(User, application.applicant_id)
        emailed = False
        if applicant is not None:
            notify(
                db,
                kind="decision",
                user_id=application.applicant_id,
                actor_id=user.id,
                application_id=application.id,
                title="You've been shortlisted" if made_the_cut else "An update on your application",
                message=(
                    f"You've been shortlisted for {requisition.title}. Please confirm to continue."
                    if made_the_cut
                    else f"An update on your application for {requisition.title}."
                ),
                link=f"/applicant/applications/{application.id}",
            )
            letter = body.shortlisted_letter if made_the_cut else body.not_shortlisted_letter
            emailed = send_email_safely(
                to=applicant.email,
                subject=(
                    f"You've been shortlisted: {requisition.title}"
                    if made_the_cut
                    else f"Update on your application: {requisition.title}"
                ),
                body=_greeting(applicant.full_name, letter),
            )
            if not emailed:
                failures += 1

        row = ShortlistedCandidate(
            application_id=application.id,
            applicant_name=applicant.full_name if applicant else f"Applicant {application.applicant_id}",
            rank=position if score is not None else None,
            match_score=score,
            outcome=outcome,
            emailed=emailed,
        )
        (shortlisted_rows if made_the_cut else not_shortlisted_rows).append(row)

    already_decided = []
    for application, outcome in decided:
        applicant = db.get(User, application.applicant_id)
        already_decided.append(
            ShortlistedCandidate(
                application_id=application.id,
                applicant_name=applicant.full_name if applicant else f"Applicant {application.applicant_id}",
                rank=None,
                match_score=None,
                outcome=outcome,
                emailed=False,
            )
        )

    db.commit()
    return ShortlistResult(
        shortlisted=shortlisted_rows,
        not_shortlisted=not_shortlisted_rows,
        already_decided=already_decided,
        emails_failed=failures,
    )
