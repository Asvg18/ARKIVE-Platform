"""The end-of-pipeline reads: the Final Decision Board that ranks a job's
remaining candidates, the interview results report (JSON and printable
PDF), and the Pre-201 package for a hire.
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.hr.common import PIPELINE_ROLES
from app.infra.db import get_db
from app.infra.deps import require_role
from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus
from app.models.job_requisition import JobRequisition
from app.models.user import User
from app.schemas.interview_report import InterviewReport
from app.schemas.pipeline import (
    CandidateProfile,
    FinalDecisionBoardEntry,
    FinalDecisionBoardResponse,
    Pre201Package,
)
from app.services.candidate_profile import build_candidate_profile, executive_triplet
from app.services.final_decision_export import build_final_decision_board_workbook, export_filename
from app.services.interview_report import build_interview_report
from app.services.interview_report_pdf import render_interview_report_pdf

router = APIRouter(tags=["decisions"])


def _build_final_decision_board(db: Session, requisition_id: int) -> FinalDecisionBoardResponse:
    """The ranking shared by the JSON read and the Excel export, so both
    show the same numbers in the same order.

    Only candidates whose job uses the 3-round executive shape (three
    interview stages, all submitted), matched by position in the workflow
    (see executive_triplet)."""
    requisition = db.get(JobRequisition, requisition_id)
    if requisition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Requisition not found")

    applications = db.scalars(
        select(CandidateApplication).where(CandidateApplication.requisition_id == requisition_id)
    ).all()

    entries: list[FinalDecisionBoardEntry] = []
    for application in applications:
        profile = build_candidate_profile(db, application.id)
        triplet = executive_triplet(profile.interview_ratings, "computed_score")
        if triplet is None:
            continue
        hr_score, dept_score, vp_score = triplet
        entries.append(
            FinalDecisionBoardEntry(
                application_id=profile.application_id,
                applicant_name=profile.applicant_name,
                hr_score=hr_score,
                dept_score=dept_score,
                vp_score=vp_score,
                skill_match_score=profile.match_score,
                exam_percentile=profile.exam_percentile,
                interview_rubric_score=profile.interview_rubric_score,
                executive_consensus_score=profile.evaluator_consensus_score,
                final_synthesis_score=profile.final_synthesis_score,
                overall_tier=profile.overall_tier,
            )
        )

    entries.sort(key=lambda e: (e.vp_score, e.dept_score, e.hr_score, e.skill_match_score or 0), reverse=True)

    return FinalDecisionBoardResponse(requisition_id=requisition.id, job_title=requisition.title, entries=entries)


@router.get(
    "/hr/requisitions/{requisition_id}/final-decision-board",
    response_model=FinalDecisionBoardResponse,
)
def get_final_decision_board(
    requisition_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> FinalDecisionBoardResponse:
    """The ranked board the HR Director reviews for the final call.
    Read-only: hiring and rejecting are PATCH
    /hr/applications/{id}/status."""
    return _build_final_decision_board(db, requisition_id)


@router.get("/hr/requisitions/{requisition_id}/final-decision-board/export")
def export_final_decision_board(
    requisition_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> Response:
    """The same board as an .xlsx download, built in memory
    (app.services.final_decision_export), never written to disk."""
    board = _build_final_decision_board(db, requisition_id)
    workbook_bytes = build_final_decision_board_workbook(board)
    return Response(
        content=workbook_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{export_filename(board.job_title)}"'},
    )


def _interview_report(db: Session, requisition_id: int) -> InterviewReport:
    requisition = db.get(JobRequisition, requisition_id)
    if requisition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Requisition not found")
    return build_interview_report(db, requisition)


@router.get("/hr/requisitions/{requisition_id}/interview-report", response_model=InterviewReport)
def get_interview_report(
    requisition_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> InterviewReport:
    """Whether the job's interview results report is ready, and its
    content (or who it is still waiting on)."""
    return _interview_report(db, requisition_id)


@router.get("/hr/requisitions/{requisition_id}/interview-report/pdf")
def get_interview_report_pdf(
    requisition_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> Response:
    """The report as a PDF, built in memory from the same InterviewReport
    as the JSON read. Refused until every candidate in the interviews has
    finished them."""
    report = _interview_report(db, requisition_id)
    if not report.ready:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="The interview results report is ready once every candidate in the interviews has finished them.",
        )
    pdf = render_interview_report_pdf(report)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{report.filename}"'},
    )


def _hired_at(application: CandidateApplication, profile: CandidateProfile) -> datetime:
    if profile.decision is not None:
        try:
            return datetime.fromisoformat(profile.decision.decided_at)
        except ValueError:
            # A malformed stored timestamp must not take down a hired
            # applicant's permanent record — fall back rather than 500.
            pass
    return application.updated_at


@router.get("/hr/applications/{application_id}/pre-201-package", response_model=Pre201Package)
def get_pre_201_package(
    application_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> Pre201Package:
    """A hired applicant's full record in one bundle, built from
    build_candidate_profile so it matches the Candidate Profile. Hired
    applications only."""
    application = db.get(CandidateApplication, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found")
    if application.status != ApplicationStatus.hired:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Pre-Employment Records are only available for hired applicants.",
        )

    applicant = db.get(User, application.applicant_id)
    profile = build_candidate_profile(db, application_id)

    return Pre201Package(
        application_id=application.id,
        applicant_name=applicant.full_name,
        applicant_email=applicant.email,
        job_title=profile.job_title,
        # the decision record's timestamp when there is one; updated_at
        # (which moves with any change) only for older applications
        hired_at=_hired_at(application, profile),
        resume=profile.resume,
        letter_of_intent=profile.letter_of_intent,
        shortlisting=profile.shortlisting,
        examinations=profile.examinations,
        interview_ratings=profile.interview_ratings,
        match_score=profile.match_score,
        evaluator_consensus_score=profile.evaluator_consensus_score,
        interview_rubric_score=profile.interview_rubric_score,
        exam_percentile=profile.exam_percentile,
        overall_tier=profile.overall_tier,
        final_synthesis_score=profile.final_synthesis_score,
        synthesis=profile.synthesis,
        decision=profile.decision,
    )
