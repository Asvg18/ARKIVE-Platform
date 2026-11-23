"""Shared by more than one HR route module: the role gate every HR
endpoint uses, and the requisition read-model that both `requisitions`
and `workflow` return after a write.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.dfa import is_interview_stage
from app.domain.interview_slots import round_duration
from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus, UserRole
from app.models.job_requisition import JobRequisition
from app.models.user import User
from app.schemas.pipeline import RequisitionDetail
from app.services.email import send_email_safely
from app.services.notifications import notify
from app.services.stage_labels import resolve_stage_label

# HR-pipeline-only -- Evaluator and Applicant have no real actions on
# this flow, their stages exist as data but aren't driven by them here
PIPELINE_ROLES = (UserRole.hr_admin,)


def active_candidate_count(db: Session, requisition_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(CandidateApplication)
        .where(
            CandidateApplication.requisition_id == requisition_id,
            CandidateApplication.status == ApplicationStatus.active,
        )
    )


def application_count(db: Session, requisition_id: int) -> int:
    """Every application ever made to this job, whatever became of it;
    quoted by the delete confirmation."""
    return db.scalar(
        select(func.count())
        .select_from(CandidateApplication)
        .where(CandidateApplication.requisition_id == requisition_id)
    )


#: Still in the pipeline. `flagged` counts too (waiting on HR), though the
#: Active column shows only `active`.
IN_FLIGHT_STATUSES = (ApplicationStatus.active, ApplicationStatus.flagged)


def in_flight_candidate_count(db: Session, requisition_id: int) -> int:
    """Applicants still moving through this job's pipeline: the delete
    gate. Past applications don't block it."""
    return db.scalar(
        select(func.count())
        .select_from(CandidateApplication)
        .where(
            CandidateApplication.requisition_id == requisition_id,
            CandidateApplication.status.in_(IN_FLIGHT_STATUSES),
        )
    )


def requisition_detail(db: Session, requisition: JobRequisition) -> RequisitionDetail:
    return RequisitionDetail(
        id=requisition.id,
        title=requisition.title,
        department=requisition.department,
        description=requisition.description,
        qualifications=requisition.qualifications,
        requirements=requisition.requirements,
        additional_sections=requisition.additional_sections or [],
        jd_filename=requisition.jd_filename,
        application_deadline=requisition.application_deadline,
        status=requisition.status,
        workflow_definition=requisition.workflow_definition,
        interview_round_labels=requisition.interview_round_labels,
        examination_labels=requisition.examination_labels,
        interview_durations={
            stage: round_duration(stage, requisition.interview_durations)
            for stage in requisition.workflow_definition
            if is_interview_stage(stage)
        },
        pre_screening_questions=requisition.pre_screening_questions or [],
        active_candidate_count=active_candidate_count(db, requisition.id),
    )


def ask_applicant_to_confirm_interview(
    db: Session,
    *,
    application: CandidateApplication,
    requisition: JobRequisition,
    stage_type: str,
    schedule: dict,
    actor: User,
) -> None:
    """Tells the applicant an interview round has a (new) time and that a
    confirmation is waiting -- in the app and by email. Shared by HR's Set
    Schedule and by approving an evaluator's new time (a moved time is asked
    again, in the same words), so the two can't drift apart. `actor` is the
    HR admin who set it. The caller opens the confirmation and owns
    db.commit()."""
    stage_label = resolve_stage_label(stage_type, requisition)
    notify(
        db,
        kind="schedule",
        user_id=application.applicant_id,
        actor_id=actor.id,
        application_id=application.id,
        title="Confirm your interview time",
        message=(
            f"Your {stage_label} has been scheduled for {schedule['date']} at {schedule['time']}. "
            "Please confirm you can attend."
        ),
        link=f"/applicant/applications/{application.id}",
    )
    applicant = db.get(User, application.applicant_id)
    if applicant is None:
        return
    online = schedule.get("mode") == "online"
    where_label = "Meeting Link" if online else "Location"
    where_value = schedule.get("meeting_link") if online else schedule.get("location")
    send_email_safely(
        to=applicant.email,
        subject=f"Your {stage_label} is scheduled: {requisition.title}",
        body=(
            f"Hi {applicant.full_name},\n\n"
            f"Your {stage_label} for {requisition.title} has been scheduled:\n\n"
            f"  Date: {schedule['date']}\n"
            f"  Time: {schedule['time']}\n"
            f"  {where_label}: {where_value}\n\n"
            "A confirmation is waiting in your ARKIVE account. Please sign in and "
            "confirm that you are available at this time, or tell us if you are "
            "not, and we will arrange another.\n"
        ),
    )
