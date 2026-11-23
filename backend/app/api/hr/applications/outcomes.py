"""Recording a stage's outcome by hand: an exam score, a shortlisting
call.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.hr.common import PIPELINE_ROLES
from app.domain.dfa import build_transition_table
from app.infra.db import get_db
from app.infra.deps import require_role
from app.models.candidate_application import CandidateApplication
from app.models.job_requisition import JobRequisition
from app.models.stage_instance import StageInstance
from app.models.user import User
from app.schemas.pipeline import (
    CandidateProfile,
    ExaminationResultRequest,
    ShortlistingResultRequest,
)
from app.services import shortlisting
from app.services.email import send_email_safely
from app.services.candidate_profile import build_candidate_profile, refresh_decision_brief
from app.services.notifications import notify
from app.services.stage_labels import resolve_stage_label

router = APIRouter()


@router.patch(
    "/hr/applications/{application_id}/examination-result",
    response_model=CandidateProfile,
)
def record_examination_result(
    application_id: int,
    body: ExaminationResultRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> CandidateProfile:
    application = db.get(CandidateApplication, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found")

    exam_instance = db.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == body.stage_type,
        )
    )
    if exam_instance is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="This job's workflow has no such examination stage.",
        )

    # the day it was sat -- what HR entered, else the booked session's
    # date
    taken_on = body.taken_on or ((exam_instance.payload or {}).get("schedule") or {}).get("date")
    exam_instance.payload = {
        **(exam_instance.payload or {}),
        "score": body.score,
        "taken_on": taken_on,
    }

    # tell the applicant their score is in; there is nothing for them to do
    requisition = db.get(JobRequisition, application.requisition_id)
    stage_label = resolve_stage_label(body.stage_type.value, requisition)
    notify(
        db,
        kind="application",
        user_id=application.applicant_id,
        actor_id=user.id,
        application_id=application.id,
        title="Exam result recorded",
        message=f"Your {stage_label} has been recorded for {requisition.title}. Please wait while HR reviews your results.",
        link=f"/applicant/applications/{application.id}",
    )
    applicant = db.get(User, application.applicant_id)
    if applicant is not None:
        send_email_safely(
            to=applicant.email,
            subject=f"Your {stage_label} is complete: {requisition.title}",
            body=(
                f"Hi {applicant.full_name},\n\n"
                f"Your {stage_label} for {requisition.title} has been recorded.\n\n"
                "There's nothing further for you to do right now. Please wait while HR "
                "reviews your results along with the rest of your application. You'll hear "
                "from us here, and by email, as soon as there's an update.\n"
            ),
        )
    db.commit()

    # only this candidate's brief is rewritten; the rest of the cohort
    # read stale until their own record changes (one OpenAI call, not N)
    if refresh_decision_brief(db, application_id, stage_type=body.stage_type.value):
        db.commit()

    return build_candidate_profile(db, application_id)


@router.patch(
    "/hr/applications/{application_id}/shortlisting-result",
    response_model=CandidateProfile,
)
def record_shortlisting_result(
    application_id: int,
    body: ShortlistingResultRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> CandidateProfile:
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
            detail="This job's workflow has no Shortlisting stage.",
        )

    # the same path as the bulk shortlist, including opening the
    # acceptance the candidate owes
    shortlisting.record_outcome(
        db, instance=instance, outcome=body.outcome, notes=body.notes
    )

    # only "shortlisted" notifies: "not shortlisted" is not a rejection,
    # and the application's status stays HR's separate call
    if body.outcome == "shortlisted":
        requisition = db.get(JobRequisition, application.requisition_id)
        notify(
            db,
            kind="decision",
            user_id=application.applicant_id,
            actor_id=user.id,
            application_id=application.id,
            title="You've been shortlisted",
            # The same words the bulk shortlist sends: either way the
            # applicant owes a confirmation before moving on.
            message=f"You've been shortlisted for {requisition.title}. Please confirm to continue.",
            link=f"/applicant/applications/{application.id}",
        )
        applicant = db.get(User, application.applicant_id)
        if applicant is not None:
            # names this job's real next stage; not every workflow has
            # an exam after Shortlisting
            next_stage = build_transition_table(requisition.workflow_definition).get(
                body.stage_type.value
            )
            next_part = (
                f", and your next stage is {resolve_stage_label(next_stage, requisition)}"
                if next_stage
                else ""
            )
            send_email_safely(
                to=applicant.email,
                subject=f"You've been shortlisted: {requisition.title}",
                body=(
                    f"Hi {applicant.full_name},\n\n"
                    f"Good news, you've been shortlisted for {requisition.title}{next_part}.\n\n"
                    "Please sign in to your application page and confirm that you'd still "
                    "like to go ahead. HR will then arrange the next step with you.\n"
                ),
            )
    db.commit()

    return build_candidate_profile(db, application_id)
