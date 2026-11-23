"""What an applicant is shown of their own application (to_detail): the
stage payloads they may see, exam and interview choices, and results.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.decision_support import compute_percentile_rank
from app.domain.dfa import is_exam_stage, is_interview_stage
from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus, StageType
from app.models.exam_slot import ExamSlot
from app.models.job_requisition import JobRequisition
from app.models.stage_instance import StageInstance
from app.schemas.applicant import (
    ApplicantExamResult,
    ApplicationDetail,
    ExamBookingSummary,
    ExamNoneWorkRead,
    ExamSlotOption,
    InterviewSlotOfferRead,
    InterviewSlotOption,
    OfferRead,
    ShortlistingAcceptanceRead,
    StageInstanceRead,
)
from app.schemas.application_document import ApplicationDocumentRead
from app.services import exam_scheduling, interview_scheduling, offers, shortlisting
from app.services.application_documents import list_application_documents
from app.services.resume_profile import get_application_resume, to_resume_read
from app.services.skill_matching import live_suggestions
from app.services.stage_labels import resolve_stage_label


def _redact_skill_matching_payload(payload: dict | None) -> dict | None:
    """The applicant's view of the skill-matching payload: their own
    answers and, if flagged, the suggested openings as id/title/department
    only. Scores, breakdowns and the AI's analysis are HR-only, and are
    removed here at the API boundary rather than hidden in the UI."""
    if payload is None:
        return None
    redacted: dict = {}
    if "answers" in payload:
        redacted["answers"] = payload["answers"]
    if "suggested_requisitions" in payload:
        redacted["suggested_requisitions"] = [
            {
                "requisition_id": r["requisition_id"],
                "title": r["title"],
                "department": r["department"],
            }
            for r in payload["suggested_requisitions"]
        ]
    return redacted


def _applicant_visible_payload(stage_type: StageType, payload: dict | None) -> dict | None:
    """Return only the payload fields the applicant may see for this stage.

    An allow-list, so a field added later stays private (evaluator remarks,
    scores, HR's decision notes) until it is let out deliberately.
    """
    if payload is None:
        return None

    if stage_type == StageType.skill_matching:
        return _redact_skill_matching_payload(payload)

    stage = stage_type.value
    if is_exam_stage(stage):
        # score is already surfaced separately via
        # ApplicationDetail.examination_results
        allowed: tuple[str, ...] = ("schedule", "score")
    elif is_interview_stage(stage):
        # the schedule and its confirmation; never the evaluation
        allowed = ("schedule", "schedule_confirmation")
    elif stage == StageType.document_upload.value:
        allowed = ("letter_of_intent",)
    elif stage == StageType.onboarding.value:
        allowed = ("checklist",)
    else:
        # HR's own working: outcomes, decision reason, who decided
        allowed = ()
    return {key: payload[key] for key in allowed if key in payload}


def _exam_picking(
    db: Session,
    application: CandidateApplication,
    requisition: JobRequisition,
    instances: list[StageInstance],
) -> tuple[list[ExamSlotOption], ExamBookingSummary | None, ExamNoneWorkRead | None]:
    """What the applicant's Examination stage shows: the sessions they can
    pick, the session they're booked in, and whether they've said none of
    the sessions work.

    Only while they're on an exam stage; empty otherwise. Once booked, the
    other sessions are listed only while they can still change (until 24
    hours before). A hand-typed schedule from before sessions existed has
    no session to change from."""
    stage = application.current_stage
    if application.status != ApplicationStatus.active or stage is None or not is_exam_stage(stage.value):
        return [], None, None
    instance = next((i for i in instances if i.stage_type == stage), None)
    if instance is None:
        return [], None, None
    payload = instance.payload or {}

    def options(exclude: int | None = None) -> list[ExamSlotOption]:
        return [
            ExamSlotOption(
                id=slot.id,
                date=slot.date,
                time=slot.time,
                end_time=slot.end_time,
                location=slot.location,
                remaining_capacity=remaining,
            )
            for slot, remaining in exam_scheduling.open_sessions(
                db, requisition_id=requisition.id, stage_type=stage.value, exclude_slot_id=exclude
            )
        ]

    booking = exam_scheduling.current_booking(db, instance)
    slot = db.get(ExamSlot, booking.exam_slot_id) if booking else None
    if slot is not None:
        can_change = exam_scheduling.applicant_can_change(slot)
        summary = ExamBookingSummary(
            stage_type=stage,
            slot_id=slot.id,
            date=slot.date,
            time=slot.time,
            end_time=slot.end_time,
            location=slot.location,
            can_change=can_change,
        )
        return (options(exclude=slot.id) if can_change else []), summary, None
    if payload.get("schedule"):
        return [], None, None
    none_work = payload.get("exam_none_work")
    return options(), None, ExamNoneWorkRead(**none_work) if none_work else None


def _interview_slot_offer(
    db: Session,
    application: CandidateApplication,
    requisition: JobRequisition,
    instances: list[StageInstance],
) -> InterviewSlotOfferRead | None:
    """The times HR sent for the interview round the applicant is on,
    while that round isn't booked yet. Only slots still free are listed:
    one taken by another candidate of the same evaluator drops out."""
    stage = application.current_stage
    if application.status != ApplicationStatus.active or stage is None or not is_interview_stage(stage.value):
        return None
    instance = next((i for i in instances if i.stage_type == stage), None)
    offer = interview_scheduling.read_offer(instance)
    if instance is None or offer is None or (instance.payload or {}).get("schedule"):
        return None
    return InterviewSlotOfferRead(
        stage_type=stage,
        duration_minutes=offer.get("duration_minutes") or 45,
        mode=offer.get("mode") or "in_person",
        location=offer.get("location"),
        slots=[
            InterviewSlotOption(date=slot.date, time=slot.start, end_time=slot.end)
            for slot in interview_scheduling.open_offer_slots(db, instance, requisition)
        ],
        response=offer.get("response"),
        note=offer.get("note"),
    )


def _applicant_exam_results(
    db: Session, requisition: JobRequisition, instances: list[StageInstance]
) -> tuple[dict[str, ApplicantExamResult], float | None]:
    """The applicant's exam results and percentiles (the same Algorithm 03
    math as candidate_profile's _exam_percentile_for). Only exam stages HR
    has recorded a score for."""
    results: dict[str, ApplicantExamResult] = {}
    percentiles: list[float] = []
    for instance in instances:
        stage_str = instance.stage_type.value
        if not is_exam_stage(stage_str):
            continue
        my_score = (instance.payload or {}).get("score")
        if my_score is None:
            continue
        results[stage_str] = ApplicantExamResult(
            label=resolve_stage_label(stage_str, requisition), score=my_score
        )
        sibling_instances = db.scalars(
            select(StageInstance)
            .join(CandidateApplication, CandidateApplication.id == StageInstance.application_id)
            .where(
                CandidateApplication.requisition_id == requisition.id,
                StageInstance.stage_type == instance.stage_type,
            )
        )
        other_scores = [
            i.payload["score"] for i in sibling_instances if i.payload and i.payload.get("score") is not None
        ]
        if other_scores:
            percentiles.append(compute_percentile_rank(my_score, other_scores))
    exam_percentile = round(sum(percentiles) / len(percentiles), 1) if percentiles else None
    return results, exam_percentile


def _acceptance_read(
    db: Session, application: CandidateApplication
) -> ShortlistingAcceptanceRead | None:
    """The confirmation a shortlisted candidate owes, for their own
    screen. None when there is nothing to answer: not shortlisted, no
    shortlisting stage, or an older shortlisting with no confirmation."""
    acceptance = shortlisting.read_acceptance(db, application)
    if acceptance is None:
        return None
    return ShortlistingAcceptanceRead(
        response=acceptance.get("response"),
        opened_at=acceptance.get("opened_at"),
        responded_at=acceptance.get("responded_at"),
    )


def to_detail(db: Session, application: CandidateApplication) -> ApplicationDetail:
    """The application as its applicant sees it: every applicant route
    returns this. Stage payloads pass through _applicant_visible_payload."""
    requisition = db.get(JobRequisition, application.requisition_id)
    instances = db.scalars(
        select(StageInstance)
        .where(StageInstance.application_id == application.id)
        .order_by(StageInstance.id)
    ).all()
    stage_instances = []
    for instance in instances:
        read = StageInstanceRead.model_validate(instance)
        read.label = resolve_stage_label(read.stage_type.value, requisition)
        read.payload = _applicant_visible_payload(read.stage_type, read.payload)
        if read.payload and read.payload.get("suggested_requisitions"):
            # stored when the score was; a job since closed, or since
            # applied to, is no longer a suggestion
            read.payload["suggested_requisitions"] = live_suggestions(
                db, applicant_id=application.applicant_id, suggestions=read.payload["suggested_requisitions"]
            )
        stage_instances.append(read)

    examination_results, exam_percentile = _applicant_exam_results(db, requisition, instances)
    exam_sessions, exam_booking, exam_none_work = _exam_picking(db, application, requisition, instances)
    offer = offers.read_offer(db, application)
    return ApplicationDetail(
        id=application.id,
        requisition_id=application.requisition_id,
        job_title=requisition.title,
        job_department=requisition.department,
        current_stage=application.current_stage,
        status=application.status,
        stage_instances=stage_instances,
        resume=to_resume_read(get_application_resume(db, application.id)),
        # not stage-gated: applicants need the question text to review
        # the answers they saved at pre-screening
        pre_screening_questions=requisition.pre_screening_questions or [],
        exam_sessions=exam_sessions,
        exam_booking=exam_booking,
        exam_none_work=exam_none_work,
        interview_slot_offer=_interview_slot_offer(db, application, requisition, instances),
        examination_results=examination_results,
        exam_percentile=exam_percentile,
        documents=[
            ApplicationDocumentRead.model_validate(d) for d in list_application_documents(db, application.id)
        ],
        offer=OfferRead.model_validate(offer) if offer else None,
        shortlisting_acceptance=_acceptance_read(db, application),
    )
