"""HR's landing summary -- the counts and at-a-glance rows on the
command centre.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.hr.common import PIPELINE_ROLES
from app.infra.db import get_db
from app.infra.deps import require_role
from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus, RequisitionStatus, StageType
from app.models.job_requisition import JobRequisition
from app.models.user import User
from app.schemas.pipeline import DashboardSummary, RequisitionSummary

router = APIRouter(tags=["dashboard"])


@router.get("/hr/dashboard/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> DashboardSummary:
    open_requisitions = db.scalar(
        select(func.count()).select_from(JobRequisition).where(JobRequisition.status == RequisitionStatus.open)
    )
    active_candidates = db.scalar(
        select(func.count())
        .select_from(CandidateApplication)
        .where(CandidateApplication.status == ApplicationStatus.active)
    )
    pending_final_approvals = db.scalar(
        select(func.count())
        .select_from(CandidateApplication)
        .where(
            CandidateApplication.status == ApplicationStatus.active,
            CandidateApplication.current_stage == StageType.final_decision,
        )
    )

    # approximated as updated_at - created_at (no hired_at column). None,
    # not 0, when nobody has been hired yet
    hired_rows = db.execute(
        select(CandidateApplication.created_at, CandidateApplication.updated_at).where(
            CandidateApplication.status == ApplicationStatus.hired
        )
    ).all()
    avg_time_to_hire_days = None
    if hired_rows:
        days = [(updated_at - created_at).total_seconds() / 86400 for created_at, updated_at in hired_rows]
        avg_time_to_hire_days = round(sum(days) / len(days), 1)

    requisitions = []
    for requisition in db.scalars(
        select(JobRequisition).where(JobRequisition.status == RequisitionStatus.open).order_by(JobRequisition.id)
    ):
        active_count = db.scalar(
            select(func.count())
            .select_from(CandidateApplication)
            .where(
                CandidateApplication.requisition_id == requisition.id,
                CandidateApplication.status == ApplicationStatus.active,
            )
        )
        requisitions.append(
            RequisitionSummary(
                id=requisition.id,
                title=requisition.title,
                department=requisition.department,
                active_candidate_count=active_count,
            )
        )

    return DashboardSummary(
        open_requisitions=open_requisitions,
        active_candidates=active_candidates,
        pending_final_approvals=pending_final_approvals,
        avg_time_to_hire_days=avg_time_to_hire_days,
        requisitions=requisitions,
    )
