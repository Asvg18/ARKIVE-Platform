"""A requisition's configured hiring pipeline -- which stages it uses,
in what order, and the pre-screening questions asked during them.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.hr.common import PIPELINE_ROLES, active_candidate_count, requisition_detail
from app.domain.workflow_rules import validate_workflow, workflow_errors
from app.infra.db import get_db
from app.infra.deps import require_role
from app.models.job_requisition import JobRequisition
from app.models.user import User
from app.schemas.pipeline import (
    PreScreeningQuestionsUpdateRequest,
    RequisitionDetail,
    WorkflowIssueRead,
    WorkflowUpdateRequest,
    WorkflowValidationRequest,
    WorkflowValidationResponse,
)

router = APIRouter(tags=["workflow"])


@router.patch("/hr/requisitions/{requisition_id}/workflow", response_model=RequisitionDetail)
def update_requisition_workflow(
    requisition_id: int,
    body: WorkflowUpdateRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> RequisitionDetail:
    """Workflow Builder save.

    The **stage sequence** is locked once the job has any active
    candidate -- their in-flight StageInstance rows were generated from
    workflow_definition at apply time, and the DFA validator reads it
    live on every transition, so reordering under them could invalidate
    their current_stage.

    The **round and examination names** are not: they are display-only,
    so a request that leaves the sequence untouched (a rename) is always
    allowed."""
    requisition = db.get(JobRequisition, requisition_id)
    if requisition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Requisition not found")

    requested_stages = [s.value for s in body.stages]
    sequence_changed = requested_stages != requisition.workflow_definition
    if sequence_changed and active_candidate_count(db, requisition.id) > 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                "This job's stage sequence can't be changed while it has active candidates. "
                "Renaming a round or an examination, the evaluator pool and the exam slots "
                "are all still editable."
            ),
        )

    # workflow rules only on a real sequence change, so older workflows
    # and label-only saves are never refused; only errors block
    if sequence_changed:
        errors = workflow_errors(requested_stages)
        if errors:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=" ".join(errors))

    requisition.workflow_definition = requested_stages
    if body.interview_round_labels is not None:
        requisition.interview_round_labels = body.interview_round_labels
    if body.examination_labels is not None:
        requisition.examination_labels = body.examination_labels
    if body.interview_durations is not None:
        requisition.interview_durations = {
            stage: minutes for stage, minutes in body.interview_durations.items() if stage in requested_stages
        }
    db.commit()
    db.refresh(requisition)
    return requisition_detail(db, requisition)


@router.post("/hr/requisitions/validate-workflow", response_model=WorkflowValidationResponse)
def validate_requisition_workflow(
    body: WorkflowValidationRequest,
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> WorkflowValidationResponse:
    """The Workflow Builder's live checklist: the save's own rules
    (workflow_rules) applied to a proposed stage list, before saving."""
    return WorkflowValidationResponse(
        issues=[
            WorkflowIssueRead(severity=issue.severity, code=issue.code, message=issue.message)
            for issue in validate_workflow([s.value for s in body.stages])
        ]
    )


@router.patch(
    "/hr/requisitions/{requisition_id}/pre-screening-questions",
    response_model=RequisitionDetail,
)
def update_pre_screening_questions(
    requisition_id: int,
    body: PreScreeningQuestionsUpdateRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> RequisitionDetail:
    """Saves the job's pre-screening questions. Locked while the job has
    an active candidate, like /workflow, so answered questions are never
    changed under an applicant."""
    requisition = db.get(JobRequisition, requisition_id)
    if requisition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Requisition not found")

    active_count = active_candidate_count(db, requisition.id)
    if active_count > 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This job's pre-screening questions can't be edited while it has active candidates.",
        )

    requisition.pre_screening_questions = [q.model_dump() for q in body.questions]
    db.commit()
    db.refresh(requisition)
    return requisition_detail(db, requisition)
