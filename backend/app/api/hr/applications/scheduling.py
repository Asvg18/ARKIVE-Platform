"""Scheduling an interview round: setting its time by hand, or sending
the evaluator's free slots for the applicant to pick.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.hr.common import ask_applicant_to_confirm_interview, PIPELINE_ROLES
from app.infra.db import get_db
from app.infra.deps import require_role
from app.models.candidate_application import CandidateApplication
from app.models.job_requisition import JobRequisition
from app.models.stage_instance import StageInstance
from app.models.user import User
from app.schemas.pipeline import (
    CandidateProfile,
    InterviewScheduleRequest,
    InterviewSlotOfferRequest,
)
from app.services import interview_scheduling, schedule_confirmation
from app.services.email import send_email_safely
from app.services.candidate_profile import build_candidate_profile
from app.services.notifications import notify
from app.services.stage_labels import resolve_stage_label

router = APIRouter()


@router.post(
    "/hr/applications/{application_id}/interview-schedule",
    response_model=CandidateProfile,
)
def set_interview_schedule(
    application_id: int,
    body: InterviewScheduleRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> CandidateProfile:
    """HR sets the date, time, and a location or online link for one of
    the interview rounds, in the same schedule shape every screen reads.
    Notifies the applicant in the app and by email."""
    application = db.get(CandidateApplication, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found")

    instance = db.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == body.stage_type,
        )
    )
    if instance is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="This job's workflow has no such interview stage.",
        )

    instance.payload = {
        **(instance.payload or {}),
        "schedule": {
            "date": body.date,
            "time": body.time,
            "mode": body.mode,
            "location": body.location,
            "meeting_link": body.meeting_link,
        },
    }
    # asks the candidate to confirm; a new time is asked afresh
    schedule_confirmation.open_confirmation(instance)
    requisition = db.get(JobRequisition, application.requisition_id)
    ask_applicant_to_confirm_interview(
        db,
        application=application,
        requisition=requisition,
        stage_type=body.stage_type.value,
        schedule=instance.payload["schedule"],
        actor=user,
    )
    db.commit()

    return build_candidate_profile(db, application_id)


@router.post(
    "/hr/applications/{application_id}/interview-slots",
    response_model=CandidateProfile,
)
def send_interview_slots(
    application_id: int,
    body: InterviewSlotOfferRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> CandidateProfile:
    """HR sends the evaluator's free slots it kept ticked to the applicant, who
    picks one. Every slot must still be free. Sending again replaces the
    earlier set -- and any time already booked on this round, so the
    applicant picks afresh. Set Schedule stays as the way to fix a time by
    hand."""
    application = db.get(CandidateApplication, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found")

    instance = db.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == body.stage_type,
        )
    )
    if instance is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="This job's workflow has no such interview stage.",
        )
    if (instance.payload or {}).get("evaluation"):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This interview has already been evaluated.")

    requisition = db.get(JobRequisition, application.requisition_id)
    try:
        offer = interview_scheduling.send_offer(
            db,
            instance=instance,
            requisition=requisition,
            slots=[(slot.date, slot.time) for slot in body.slots],
            mode=body.mode,
            location=(body.location or "").strip() or None,
            meeting_link=(body.meeting_link or "").strip() or None,
        )
    except interview_scheduling.SlotUnavailableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    stage_label = resolve_stage_label(body.stage_type.value, requisition)
    count = len(offer["slots"])
    notify(
        db,
        kind="schedule",
        user_id=application.applicant_id,
        actor_id=user.id,
        application_id=application.id,
        title="Pick an interview time",
        message=f"Pick a time for your {stage_label}: {count} time{'s' if count != 1 else ''} to choose from.",
        link=f"/applicant/applications/{application.id}",
    )
    applicant = db.get(User, application.applicant_id)
    if applicant is not None:
        where = (
            "Online (the meeting link is shown once you pick a time)"
            if body.mode == "online"
            else f"In person, at {offer['location']}"
        )
        send_email_safely(
            to=applicant.email,
            subject=f"Pick a time for your {stage_label}: {requisition.title}",
            body=(
                f"Hi {applicant.full_name},\n\n"
                f"HR has sent you {count} time{'s' if count != 1 else ''} to choose from for your "
                f"{stage_label} for {requisition.title}.\n\n"
                f"  Where: {where}\n"
                f"  Length: {offer['duration_minutes']} minutes\n\n"
                "Please sign in to your application page and pick the one that suits you. "
                "If none of them work, you can tell HR there, and they will send others.\n"
            ),
        )
    db.commit()

    return build_candidate_profile(db, application_id)
