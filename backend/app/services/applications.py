"""Creating an application's stage instances and moving it between
stages; every caller goes through these same rules.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.dfa import InvalidTransitionError, validate_transition
from app.domain.stage_requirements import StageRequirementsUnmetError, transition_blockers
from app.models.application_resume import ApplicationResume
from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus, StageStatus, StageType
from app.models.job_requisition import JobRequisition
from app.models.stage_history import StageHistory
from app.models.stage_instance import StageInstance


class ApplicationWorkflow:
    """Session-scoped wrapper. The module-level functions below just delegate
    to this — kept around so existing routes/scripts/tests didn't all need
    updating when this class was introduced.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self, *, applicant_id: int, requisition: JobRequisition
    ) -> CandidateApplication:
        return _create_application_with_stage_instances(
            self.db, applicant_id=applicant_id, requisition=requisition
        )

    def transition(
        self,
        *,
        application: CandidateApplication,
        requisition: JobRequisition,
        target_stage: StageType,
        triggered_by: str,
        current_stage_payload: dict | None = None,
        allow_incomplete: bool = False,
        incomplete_reason: str | None = None,
    ) -> CandidateApplication:
        return _transition_application_stage(
            self.db,
            application=application,
            requisition=requisition,
            target_stage=target_stage,
            triggered_by=triggered_by,
            current_stage_payload=current_stage_payload,
            allow_incomplete=allow_incomplete,
            incomplete_reason=incomplete_reason,
        )


def create_application_with_stage_instances(
    db: Session, *, applicant_id: int, requisition: JobRequisition
) -> CandidateApplication:
    return ApplicationWorkflow(db).create(
        applicant_id=applicant_id, requisition=requisition
    )


def _create_application_with_stage_instances(
    db: Session, *, applicant_id: int, requisition: JobRequisition
) -> CandidateApplication:
    """Pre-generates one StageInstance per workflow stage (first one
    `in_progress`, rest `pending`), keeping current_stage pointed at the
    same one — these two must never drift apart.

    Stages are coerced to StageType explicitly: SQLAlchemy only coerces
    on a database round-trip, so within the session they would be str."""
    workflow = requisition.workflow_definition
    application = CandidateApplication(
        applicant_id=applicant_id,
        requisition_id=requisition.id,
        current_stage=StageType(workflow[0]),
    )
    db.add(application)
    db.flush()  # need application.id before the StageInstance FKs below can point at it

    for i, stage_type in enumerate(workflow):
        db.add(
            StageInstance(
                application_id=application.id,
                stage_type=StageType(stage_type),
                status=StageStatus.in_progress if i == 0 else StageStatus.pending,
            )
        )
    # flush (not just add) so these rows are actually visible before the
    # caller commits -- transition_application_stage does its own SELECT
    # for the current StageInstance, and under autoflush=False (that's
    # what tests/conftest.py uses) it'd miss these and create a duplicate
    db.flush()

    return application


def transition_application_stage(
    db: Session,
    *,
    application: CandidateApplication,
    requisition: JobRequisition,
    target_stage: StageType,
    triggered_by: str,
    current_stage_payload: dict | None = None,
    allow_incomplete: bool = False,
    incomplete_reason: str | None = None,
) -> CandidateApplication:
    return ApplicationWorkflow(db).transition(
        application=application,
        requisition=requisition,
        target_stage=target_stage,
        triggered_by=triggered_by,
        current_stage_payload=current_stage_payload,
        allow_incomplete=allow_incomplete,
        incomplete_reason=incomplete_reason,
    )


# Statuses that refuse every stage move. A flagged application is frozen
# until HR clears it through resolve-flag (which sets it back to active
# *before* moving it), so still being flagged here means something is
# routing around the review gate. A withdrawn one is frozen for good.
_FROZEN_STATUS_REASONS = {
    ApplicationStatus.flagged: "This application is flagged for review. Resolve the flag before advancing.",
    ApplicationStatus.withdrawn: "This application has been withdrawn by the applicant.",
}


def _transition_application_stage(
    db: Session,
    *,
    application: CandidateApplication,
    requisition: JobRequisition,
    target_stage: StageType,
    triggered_by: str,
    current_stage_payload: dict | None = None,
    allow_incomplete: bool = False,
    incomplete_reason: str | None = None,
) -> CandidateApplication:
    """Advance `application` to `target_stage`. Used by every caller (HR,
    applicant submissions, seed script), so all get both gates. Caller
    owns db.commit().

    Two gates: the DFA (validate_transition) checks the move is *legal*,
    raising InvalidTransitionError and touching nothing; then the stage
    being left must have *produced* its evidence, else
    StageRequirementsUnmetError.

    `current_stage_payload` is written onto the stage being completed
    before the check. `allow_incomplete` (HR's route only) overrides the
    second gate: the stage is then recorded `skipped`, not `complete`,
    with the reason and actor on its payload.
    """
    current_stage = application.current_stage.value if application.current_stage else None

    if application.status in _FROZEN_STATUS_REASONS:
        raise InvalidTransitionError(
            current_stage=current_stage,
            target_stage=target_stage.value,
            reason=_FROZEN_STATUS_REASONS[application.status],
        )

    validate_transition(requisition.workflow_definition, current_stage, target_stage.value)

    current_instance = db.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == application.current_stage,
            StageInstance.status == StageStatus.in_progress,
        )
    )
    if current_instance is not None:
        if current_stage_payload is not None:
            current_instance.payload = current_stage_payload

        # checks the payload as it will be *saved*, since a submission
        # carries its own evidence; only TRANSITION_BLOCKING_KEYS block
        stage_key = (
            current_instance.stage_type.value
            if hasattr(current_instance.stage_type, "value")
            else str(current_instance.stage_type)
        )
        # we actually look this up instead of leaving it None -- resume
        # lives in application_resumes, not on the payload, so the pure
        # rule module can't see it and someone has to check. leaving it
        # unset silently disables the resume rule.
        has_resume = None
        if stage_key == StageType.document_upload.value:
            has_resume = (
                db.scalar(
                    select(ApplicationResume.id).where(
                        ApplicationResume.application_id == application.id
                    )
                )
                is not None
            )
        missing = transition_blockers(
            stage_key, current_instance.payload, has_resume=has_resume
        )
        if missing and not allow_incomplete:
            raise StageRequirementsUnmetError(stage=stage_key, missing=missing)

        if missing:
            # skipped, not complete -- this status has been sitting in the
            # vocabulary since the first migration with nothing ever
            # writing it. this is exactly the case it was meant for, and
            # the applicant UI already knows how to render it.
            current_instance.status = StageStatus.skipped
            current_instance.payload = {
                **(current_instance.payload or {}),
                "skipped": {
                    "reason": incomplete_reason,
                    "missing": [item.key for item in missing],
                    "acknowledged_by": triggered_by,
                    "acknowledged_at": datetime.now(timezone.utc).isoformat(),
                },
            }
        else:
            current_instance.status = StageStatus.complete
        current_instance.completed_at = datetime.now(timezone.utc)

    next_instance = db.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == target_stage,
        )
    )
    if next_instance is not None:
        next_instance.status = StageStatus.in_progress
    else:
        db.add(
            StageInstance(
                application_id=application.id,
                stage_type=target_stage,
                status=StageStatus.in_progress,
            )
        )

    db.add(
        StageHistory(
            application_id=application.id,
            from_stage=application.current_stage,
            to_stage=target_stage,
            triggered_by=triggered_by,
        )
    )

    application.current_stage = target_stage
    return application
