"""The Candidate Profile every HR screen reads (build_candidate_profile),
and refreshing its Decision Brief on writes (refresh_decision_brief).
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.rag_dfa import TERMINAL as UNVERIFIED_TERMINAL_STATES
from app.domain.decision_support import (
    compute_final_synthesis_score,
    compute_percentile_rank,
    compute_weighted_consensus,
)
from app.domain.dfa import build_transition_table, is_exam_stage, is_interview_stage
from app.domain.interview_slots import round_duration
from app.domain.scorecard import compute_tier
from app.models.candidate_application import CandidateApplication
from app.models.enums import (
    ApplicationStatus,
    ExamBookingStatus,
    RescheduleRequestStatus,
    StageType,
)
from app.models.exam_slot import ExamSlot
from app.models.exam_slot_booking import ExamSlotBooking
from app.models.interview_reschedule_request import InterviewRescheduleRequest
from app.models.job_requisition import JobRequisition
from app.models.stage_instance import StageInstance
from app.models.user import User
from app.schemas.application_document import ApplicationDocumentRead
from app.schemas.pipeline import (
    CandidateProfile,
    ExamBookingCandidateSlot,
    ExamBookingRead,
    PreScreeningQAEntry,
)
from app.schemas.synthesis import DisputedRequirement
from app.schemas.user import avatar_url
from app.services import exam_scheduling, interview_scheduling
from app.services.application_documents import list_application_documents
from app.services.decision_brief import BriefFacts, latest_brief, run_decision_brief
from app.services.hire_decision import read_decision_record
from app.services.jd_extraction import AIExtractionFailedError, ExtractionNotConfiguredError
from app.services.resume_profile import get_application_resume, to_resume_read
from app.services.skill_matching import live_suggestions, read_match_breakdown
from app.services.stage_labels import resolve_stage_label
from app.services.synthesis import build_synthesis

__all__ = [
    "build_candidate_profile",
    "executive_triplet",
    "match_score_for",
    "refresh_decision_brief",
]


_NEXT_STEP_LABELS: dict[str, str] = {
    "document_upload": "Waiting on the candidate to upload documents.",
    "skill_matching": "Waiting on the pre-screening step to complete.",
    "shortlisting": "Decide whether to shortlist this candidate.",
    "final_decision": "Make the final hire/reject decision.",
    "onboarding": "Send onboarding materials.",
}

def _exam_booking_read(db: Session, booking: ExamSlotBooking) -> ExamBookingRead:
    """The applicant's selected slots as full objects, so HR can offer an
    alternative without a second request."""
    candidate_slots = db.scalars(
        select(ExamSlot).where(ExamSlot.id.in_(booking.applicant_selected_slot_ids))
    ).all()
    return ExamBookingRead(
        id=booking.id,
        proposed_slot_id=booking.exam_slot_id,
        candidate_slots=[
            ExamBookingCandidateSlot(id=s.id, date=s.date, time=s.time, location=s.location)
            for s in candidate_slots
        ],
    )

def match_score_for(db: Session, application_id: int) -> float | None:
    match_instance = db.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application_id,
            StageInstance.stage_type == StageType.skill_matching,
        )
    )
    if match_instance is None or not match_instance.payload:
        return None
    # no `pending` check: the score is written at resume upload, before
    # this stage starts (api/applicant/documents._score_resume_against_job)
    return match_instance.payload.get("match_score")

def executive_triplet(interview_ratings: dict[str, dict], field: str) -> tuple[float, float, float] | None:
    """The three scores Algorithm 04 weights as HR / Dept Head / VP, in
    that order — or None if this workflow isn't the 3-round executive
    shape the algorithm assumes, or not everyone's submitted yet.

    Matched by *position* in the workflow, not by stage name: jobs
    created before the evaluator redesign use older stage names, and
    matching by name would skip the weighting for all of them.

    Shared by _consolidate_executive_scores and the Final Decision Board,
    so their rules match."""
    ordered = list(interview_ratings)
    if len(ordered) != 3:
        return None
    scores = [interview_ratings[stage][field] for stage in ordered]
    if any(s is None for s in scores):
        return None
    return scores[0], scores[1], scores[2]

def _consolidate_executive_scores(interview_ratings: dict[str, dict], field: str) -> float | None:
    """Algorithm 04's 30/30/40 weighting when executive_triplet applies,
    else a plain mean of the submitted rounds."""
    triplet = executive_triplet(interview_ratings, field)
    if triplet is not None:
        return compute_weighted_consensus(*triplet)

    scores = [r[field] for r in interview_ratings.values() if r[field] is not None]
    return round(sum(scores) / len(scores), 2) if scores else None

def _exam_percentile_for(db: Session, requisition_id: int, examinations: dict[str, dict]) -> float | None:
    """Algorithm 03: this candidate's percentile rank against every other
    score on the same job and exam stage, averaged across exam stages."""
    percentiles: list[float] = []
    for stage_str, exam in examinations.items():
        my_score = exam["score"]
        if my_score is None:
            continue
        sibling_instances = db.scalars(
            select(StageInstance)
            .join(CandidateApplication, CandidateApplication.id == StageInstance.application_id)
            .where(
                CandidateApplication.requisition_id == requisition_id,
                StageInstance.stage_type == StageType(stage_str),
            )
        )
        other_scores = [
            i.payload["score"] for i in sibling_instances if i.payload and i.payload.get("score") is not None
        ]
        if other_scores:
            percentiles.append(compute_percentile_rank(my_score, other_scores))
    return round(sum(percentiles) / len(percentiles), 1) if percentiles else None

def refresh_decision_brief(db: Session, application_id: int, *, stage_type: str) -> bool:
    """Rewrites the Decision Brief if the record has changed since the last
    one. Called only from write paths, never from a read (the profile is
    polled every 8 seconds; each brief is an OpenAI call).

    Never raises: the write must succeed even if OpenAI is down, and the
    old brief then shows as stale. Uses the synthesis's own facts, so the
    stored fingerprint matches.
    """
    try:
        synthesis = build_candidate_profile(db, application_id).synthesis
    except HTTPException:
        return False

    stored = latest_brief(db, application_id)
    if stored and stored.get("fingerprint") == synthesis.fact_fingerprint:
        return False

    try:
        run_decision_brief(
            db,
            application_id=application_id,
            stage_type=stage_type,
            facts=BriefFacts(
                lines=synthesis.fact_sheet, fingerprint=synthesis.fact_fingerprint
            ),
        )
    except (AIExtractionFailedError, ExtractionNotConfiguredError):
        return False
    return True

def _exam_standing_for(
    db: Session, requisition_id: int, examinations: dict[str, dict]
) -> tuple[int | None, int | None]:
    """This candidate's rank and cohort size — "1st of 3".

    The first scored exam stage only (an average of ranks is not a rank).
    Ties share the better rank: two on 88 are both 1st, the next is 3rd.
    """
    for stage_str, exam in examinations.items():
        my_score = exam["score"]
        if my_score is None:
            continue
        sibling_instances = db.scalars(
            select(StageInstance)
            .join(CandidateApplication, CandidateApplication.id == StageInstance.application_id)
            .where(
                CandidateApplication.requisition_id == requisition_id,
                StageInstance.stage_type == StageType(stage_str),
            )
        )
        scores = [
            i.payload["score"]
            for i in sibling_instances
            if i.payload and i.payload.get("score") is not None
        ]
        if not scores:
            continue
        return sum(1 for s in scores if s > my_score) + 1, len(scores)
    return None, None


def _pre_screening_qa(requisition: JobRequisition, match_payload: dict | None) -> list[PreScreeningQAEntry]:
    """Each pre-screening answer beside its question. The question text
    comes from the job, the answer from the skill_matching payload; a
    deleted question falls back to its id."""
    question_text_by_id = {q["id"]: q["text"] for q in (requisition.pre_screening_questions or [])}
    pre_screening_qa = []
    for i, a in enumerate(match_payload.get("answers", []) if match_payload else []):
        if isinstance(a, dict):
            pre_screening_qa.append(
                PreScreeningQAEntry(
                    question_id=a["question_id"],
                    question_text=question_text_by_id.get(a["question_id"], a["question_id"]),
                    answer=a["value"],
                )
            )
        else:
            # Legacy answers (a plain list, no question_id) are not paired
            # with questions by position: HR may have reordered, added or
            # removed questions since. Show them as unidentified rather
            # than guess.
            pre_screening_qa.append(
                PreScreeningQAEntry(
                    question_id=f"legacy-{i}",
                    question_text="(Legacy submission: original question no longer tracked)",
                    answer=a,
                )
            )
    return pre_screening_qa


def _interview_ratings(
    db: Session, requisition: JobRequisition, instances: dict[StageType, StageInstance]
) -> dict[str, dict]:
    """One entry per interview round in this job's workflow: the assigned
    evaluator, the submitted scorecard (if any), the schedule and its
    confirmation, the evaluator → HR → applicant slots, and any pending
    reschedule request."""
    interview_ratings: dict[str, dict] = {}
    for stage_str in requisition.workflow_definition:
        if not is_interview_stage(stage_str):
            continue
        instance = instances.get(StageType(stage_str))
        if instance is None:
            continue
        # included while pending: HR assigns and schedules ahead of time
        payload = instance.payload or {}
        evaluation = payload.get("evaluation")
        assigned_evaluator = (
            db.get(User, instance.assigned_evaluator_id) if instance.assigned_evaluator_id else None
        )
        pending_request = db.scalar(
            select(InterviewRescheduleRequest).where(
                InterviewRescheduleRequest.stage_instance_id == instance.id,
                InterviewRescheduleRequest.status == RescheduleRequestStatus.pending,
            )
        )
        # .get(), not indexing: evaluations from before the HRD-F-APIEF
        # scorecard have only the old single `rating` and none of these
        # fields. The old rating is not mapped onto computed_score, since
        # the scales differ -- show None rather than guess.
        interview_ratings[stage_str] = {
            "label": resolve_stage_label(stage_str, requisition),
            "assigned_evaluator_id": instance.assigned_evaluator_id,
            "assigned_evaluator_name": assigned_evaluator.full_name if assigned_evaluator else None,
            "assigned_evaluator_avatar_url": avatar_url(assigned_evaluator.avatar_file) if assigned_evaluator else None,
            "item_ratings": evaluation.get("item_ratings") if evaluation else None,
            "computed_score": evaluation.get("computed_score") if evaluation else None,
            "tier": evaluation.get("tier") if evaluation else None,
            # None on older evaluations; never inferred from the tier
            "recommendation": evaluation.get("recommendation") if evaluation else None,
            "remarks": evaluation.get("remarks") if evaluation else None,
            "ai_summary": evaluation.get("ai_summary") if evaluation else None,
            "rubric_coverage_score": evaluation.get("rubric_coverage_score") if evaluation else None,
            "submitted_by": evaluation.get("submitted_by") if evaluation else None,
            "submitted_at": evaluation.get("submitted_at") if evaluation else None,
            "schedule": payload.get("schedule"),
            # the applicant's answer to the booked time; None for a time
            # set before confirmations existed
            "schedule_confirmation": payload.get("schedule_confirmation"),
            # evaluator → HR → applicant scheduling: the evaluator's ranges,
            # those cut into slots (taken = booked with the same evaluator
            # elsewhere), and what HR last sent the applicant
            "duration_minutes": round_duration(stage_str, requisition.interview_durations),
            "availability": [
                {"date": row.date, "start": row.start_time, "end": row.end_time}
                for row in interview_scheduling.availability_windows(db, instance)
            ],
            "slot_choices": (
                []
                if evaluation
                else [
                    {"date": slot.date, "time": slot.start, "end_time": slot.end, "taken": taken}
                    for slot, taken in interview_scheduling.slot_choices(db, instance, requisition)
                ]
            ),
            "slot_offer": interview_scheduling.read_offer(instance),
            "reschedule_request": (
                {
                    "id": pending_request.id,
                    "proposed_date": pending_request.proposed_date,
                    "proposed_time": pending_request.proposed_time,
                    "reason": pending_request.reason,
                }
                if pending_request
                else None
            ),
        }
    return interview_ratings


def _examinations(
    db: Session, requisition: JobRequisition, instances: dict[StageType, StageInstance]
) -> dict[str, dict]:
    """One entry per exam stage in the workflow, included while pending:
    the schedule and where it came from, the score HR recorded, and any
    older pending booking proposal."""
    examinations: dict[str, dict] = {}
    for stage_str in requisition.workflow_definition:
        if not is_exam_stage(stage_str):
            continue
        instance = instances.get(StageType(stage_str))
        if instance is None:
            continue
        payload = instance.payload or {}
        pending_booking = db.scalar(
            select(ExamSlotBooking).where(
                ExamSlotBooking.stage_instance_id == instance.id,
                ExamSlotBooking.status == ExamBookingStatus.pending,
            )
        )
        booking = exam_scheduling.current_booking(db, instance)
        booked_slot = db.get(ExamSlot, booking.exam_slot_id) if booking else None
        examinations[stage_str] = {
            "label": resolve_stage_label(stage_str, requisition),
            "status": instance.status.value,
            "schedule": payload.get("schedule"),
            # a session seat, or an older hand-typed time (which can
            # only be moved into a session)
            "schedule_source": (
                "session" if booked_slot else "typed" if payload.get("schedule") else None
            ),
            "booked_slot_id": booked_slot.id if booked_slot else None,
            # whether the applicant could still change it themselves
            "applicant_can_change": (
                exam_scheduling.applicant_can_change(booked_slot) if booked_slot else False
            ),
            # sessions still open for this exam, so HR's profile can say
            # how many the applicant has to pick from
            "open_sessions": len(
                exam_scheduling.open_sessions(db, requisition_id=requisition.id, stage_type=stage_str)
            ),
            "none_work": payload.get("exam_none_work"),
            # manually entered by HR, never agent output -- None until
            # they've actually recorded it
            "score": payload.get("score"),
            # the day it was sat, recorded with the score
            "taken_on": payload.get("taken_on"),
            "pending_booking": _exam_booking_read(db, pending_booking) if pending_booking else None,
        }
    return examinations


def _shortlisting(requisition: JobRequisition, instances: dict[StageType, StageInstance]) -> dict[str, dict]:
    """The shortlisting call, dict-keyed like examinations, with 0 or 1
    entries."""
    shortlisting: dict[str, dict] = {}
    for stage_str in requisition.workflow_definition:
        if stage_str != "shortlisting":
            continue
        instance = instances.get(StageType(stage_str))
        if instance is None:
            continue
        payload = instance.payload or {}
        shortlisting[stage_str] = {
            "label": resolve_stage_label(stage_str, requisition),
            "status": instance.status.value,
            "outcome": payload.get("outcome"),
            "notes": payload.get("notes"),
        }
    return shortlisting


def _final_synthesis_score(
    match_score: float | None,
    exam_percentile: float | None,
    evaluator_consensus_score: float | None,
    interview_rubric_score: float | None,
) -> float | None:
    """The Weighted Sum Model (5.1.2.8) over the four criteria, or None
    unless all four are present: a missing input is never treated as
    zero."""
    if (
        match_score is not None
        and exam_percentile is not None
        and evaluator_consensus_score is not None
        and interview_rubric_score is not None
    ):
        return compute_final_synthesis_score(
            skill_score=match_score,
            exam_percentile=exam_percentile,
            # rescale 1-5 to 0-100 -- WSM assumes normalized inputs
            executive_consensus_score=evaluator_consensus_score * 20,
            interview_rubric_score=interview_rubric_score,
        )
    return None


def _next_step(application: CandidateApplication, requisition: JobRequisition) -> tuple[str | None, str]:
    """The stage the application goes to next (None while flagged, or at
    the end), and the sentence telling HR what to do now."""
    next_stage = None
    # null while flagged: frozen until resolve-flag
    if application.current_stage is not None and application.status != ApplicationStatus.flagged:
        next_stage = build_transition_table(requisition.workflow_definition).get(
            application.current_stage.value
        )
    if application.status == ApplicationStatus.flagged:
        next_steps = "Flagged by the Skill Matching Agent as a weak fit. Resolve via Reject or Approve to Continue."
    elif application.status.value != "active":
        next_steps = f"Application closed (status: {application.status.value})."
    elif application.current_stage == StageType.final_decision:
        # Approve Hire moves them onto Onboarding itself, so the step
        # here is the decision, not "Send onboarding materials".
        next_steps = "Make the final hire or reject decision."
    elif next_stage is None:
        next_steps = "Candidate has reached the terminal stage of this workflow."
    elif is_interview_stage(next_stage):
        next_steps = f"Conduct {resolve_stage_label(next_stage, requisition)}."
    elif is_exam_stage(next_stage):
        # the applicant books their own session; HR keeps sessions open
        # and records the score
        next_steps = f"Make sure {resolve_stage_label(next_stage, requisition)} has open sessions, then record the score."
    else:
        next_steps = _NEXT_STEP_LABELS.get(next_stage, f"Advance to {next_stage}.")
    return next_stage, next_steps


def build_candidate_profile(db: Session, application_id: int) -> CandidateProfile:
    """The full Candidate Profile for one application, built fresh from the
    database on every call; every route that returns a profile uses it.

    Assembled from the parts below in a fixed order: the application and
    its stage rows, pre-screening, interview rounds (and their consensus
    scores), exams, shortlisting, the stored skill match, the Weighted Sum
    Model, the next step, the synthesis and the decision record.

    A read: it does not commit and never refreshes the Decision Brief
    (see refresh_decision_brief). Raises a 404 HTTPException when the
    application does not exist."""
    application = db.get(CandidateApplication, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found")

    requisition = db.get(JobRequisition, application.requisition_id)
    applicant = db.get(User, application.applicant_id)
    instances = {
        i.stage_type: i
        for i in db.scalars(
            select(StageInstance).where(StageInstance.application_id == application.id)
        )
    }

    resume = to_resume_read(get_application_resume(db, application.id))

    document_upload_instance = instances.get(StageType.document_upload)
    letter_of_intent = (
        (document_upload_instance.payload or {}).get("letter_of_intent")
        if document_upload_instance
        else None
    )

    match_instance = instances.get(StageType.skill_matching)
    # a `pending` stage can hold a real score (see match_score_for)
    match_payload = match_instance.payload if match_instance and match_instance.payload else None

    pre_screening_qa = _pre_screening_qa(requisition, match_payload)
    interview_analysis = match_payload.get("interview_analysis") if match_payload else None

    interview_ratings = _interview_ratings(db, requisition, instances)

    # computed on every read, not stored. Algorithm 04's 30/30/40 only
    # for exactly 3 interview stages, all submitted; otherwise a plain mean
    evaluator_consensus_score = _consolidate_executive_scores(interview_ratings, "computed_score")
    # same consolidation, but over rubric_coverage_score (the AI's rating)
    # instead of computed_score (the human's) -- feeds WSM's C4 "Interview
    # Rubric Score"
    interview_rubric_score = _consolidate_executive_scores(interview_ratings, "rubric_coverage_score")

    examinations = _examinations(db, requisition, instances)
    shortlisting = _shortlisting(requisition, instances)

    # read back from the skill_matching StageInstance's payload rather
    # than recomputed -- same as match_score/top_skills below
    evaluation_summary = match_payload.get("summary") if match_payload else None
    strength_tags = match_payload.get("strengths", []) if match_payload else []
    match_gaps = match_payload.get("gaps", []) if match_payload else []
    match_trace = (match_payload or {}).get("rag_trace") or {}
    match_unverified = match_trace.get("terminal_state") in UNVERIFIED_TERMINAL_STATES
    match_disputed = [
        DisputedRequirement(requirement=check["requirement"], note=check["note"])
        for check in (match_payload or {}).get("requirement_checks", [])
        if (check.get("note") or "").startswith("Disputed")
    ]
    # stored with the score; a job since closed, or since applied to, is
    # dropped rather than shown as a suggestion
    suggested_requisitions = live_suggestions(
        db,
        applicant_id=application.applicant_id,
        suggestions=(match_payload or {}).get("suggested_requisitions") or [],
    )
    match_breakdown = read_match_breakdown(match_payload)

    # Decision Support's WSM inputs -- computed fresh on every read, same
    # as everything else above. nothing here gets persisted.
    exam_percentile = _exam_percentile_for(db, requisition.id, examinations)
    overall_tier = compute_tier(evaluator_consensus_score) if evaluator_consensus_score is not None else None
    match_score = match_payload.get("match_score") if match_payload else None
    final_synthesis_score = _final_synthesis_score(
        match_score, exam_percentile, evaluator_consensus_score, interview_rubric_score
    )

    next_stage, next_steps = _next_step(application, requisition)

    exam_rank, exam_cohort = _exam_standing_for(db, requisition.id, examinations)
    synthesis = build_synthesis(
        db,
        application_id=application.id,
        requisition=requisition,
        match_score=match_score,
        exam_percentile=exam_percentile,
        evaluator_consensus_score=evaluator_consensus_score,
        interview_rubric_score=interview_rubric_score,
        final_synthesis_score=final_synthesis_score,
        overall_tier=overall_tier,
        interview_ratings=interview_ratings,
        examinations=examinations,
        match_strengths=strength_tags,
        match_gaps=match_gaps,
        match_unverified=match_unverified,
        match_disputed=match_disputed,
        match_breakdown=match_breakdown,
        exam_rank=exam_rank,
        exam_cohort=exam_cohort,
    )

    final_decision_instance = instances.get(StageType.final_decision)
    decision = read_decision_record(
        final_decision_instance.payload if final_decision_instance else None
    )

    return CandidateProfile(
        application_id=application.id,
        requisition_id=requisition.id,
        applicant_name=applicant.full_name,
        applicant_avatar_url=avatar_url(applicant.avatar_file),
        job_title=requisition.title,
        current_stage=application.current_stage,
        current_stage_label=resolve_stage_label(
            application.current_stage.value if application.current_stage else None, requisition
        ),
        status=application.status,
        resume=resume,
        letter_of_intent=letter_of_intent,
        documents=[
            ApplicationDocumentRead.model_validate(d)
            for d in list_application_documents(db, application.id)
        ],
        match_score=match_payload.get("match_score") if match_payload else None,
        match_semantic_score=match_payload.get("semantic_score") if match_payload else None,
        match_keyword_score=match_payload.get("keyword_score") if match_payload else None,
        top_skills=match_payload.get("top_skills", []) if match_payload else [],
        shortlisting=shortlisting,
        interview_ratings=interview_ratings,
        evaluator_consensus_score=evaluator_consensus_score,
        examinations=examinations,
        evaluation_summary=evaluation_summary,
        strength_tags=strength_tags,
        match_gaps=match_gaps,
        pre_screening_qa=pre_screening_qa,
        interview_analysis_summary=interview_analysis["summary"] if interview_analysis else None,
        interview_analysis_strengths=interview_analysis["strengths"] if interview_analysis else [],
        interview_analysis_gaps=interview_analysis["gaps"] if interview_analysis else [],
        interview_rubric_score=interview_rubric_score,
        exam_percentile=exam_percentile,
        overall_tier=overall_tier,
        final_synthesis_score=final_synthesis_score,
        flagged=application.status == ApplicationStatus.flagged,
        suggested_requisitions=suggested_requisitions,
        next_stage=StageType(next_stage) if next_stage else None,
        next_stage_label=resolve_stage_label(next_stage, requisition) if next_stage else None,
        next_steps=next_steps,
        synthesis=synthesis,
        decision=decision,
    )
