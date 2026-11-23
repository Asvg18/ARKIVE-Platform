"""The generic "advance this application one stage" endpoint. Kept out
of the hr/ package because its path isn't under /hr.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.hr.common import PIPELINE_ROLES
from app.domain.dfa import InvalidTransitionError
from app.domain.stage_requirements import StageRequirementsUnmetError
from app.infra.db import get_db
from app.infra.deps import require_role
from app.models.candidate_application import CandidateApplication
from app.models.job_requisition import JobRequisition
from app.models.user import User
from app.schemas.pipeline import TransitionRequest, TransitionResponse
from app.services.applications import transition_application_stage
from app.services.stage_labels import describe_transition_error, resolve_stage_label

router = APIRouter(tags=["transitions"])


@router.post("/applications/{application_id}/transition", response_model=TransitionResponse)
def transition_application(
    application_id: int,
    body: TransitionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PIPELINE_ROLES)),
) -> TransitionResponse:
    # a nonexistent id returns 404, not 403/422, so existence isn't
    # confirmed/denied via the wrong status code. HR has full pipeline
    # access, so there's no further per-user scoping beyond existence.
    application = db.get(CandidateApplication, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found")

    requisition = db.get(JobRequisition, application.requisition_id)
    previous_stage = application.current_stage

    try:
        transition_application_stage(
            db,
            application=application,
            requisition=requisition,
            target_stage=body.target_stage,
            triggered_by=str(user.id),
            allow_incomplete=body.acknowledged_incomplete,
            incomplete_reason=body.reason,
        )
    except InvalidTransitionError as exc:
        # no writes happen above this line -- an invalid transition
        # leaves every row exactly as it was
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=describe_transition_error(exc, requisition),
        ) from exc
    except StageRequirementsUnmetError as exc:
        # 409: the move is legal but the record is incomplete, which the
        # caller can acknowledge. Same body shape as the hire gate.
        if not body.acknowledged_incomplete:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "code": "stage_incomplete",
                    "message": (
                        f"{resolve_stage_label(exc.stage, requisition)} has not recorded "
                        f"{'its ' + exc.missing[0].label.lower() if len(exc.missing) == 1 else 'everything it needs'}. "
                        "Advancing now will record the stage as skipped."
                    ),
                    "blockers": [
                        {"key": m.key, "label": m.label, "detail": m.detail} for m in exc.missing
                    ],
                },
            ) from exc
        raise

    db.commit()

    return TransitionResponse(
        application_id=application.id,
        previous_stage=previous_stage,
        current_stage=application.current_stage,
    )
