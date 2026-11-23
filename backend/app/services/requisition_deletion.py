"""Deleting a job requisition and every row that depends on it
(delete_requisition_cascade), and the files left behind.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.agent_run import AgentRun
from app.models.application_document import ApplicationDocument
from app.models.application_resume import ApplicationResume
from app.models.candidate_application import CandidateApplication
from app.models.exam_slot import ExamSlot
from app.models.exam_slot_booking import ExamSlotBooking
from app.models.interview_availability import InterviewAvailability
from app.models.interview_reschedule_request import InterviewRescheduleRequest
from app.models.job_description_version import JobDescriptionVersion
from app.models.job_requisition import JobRequisition
from app.models.notification import Notification
from app.models.requisition_evaluator import RequisitionEvaluator
from app.models.stage_history import StageHistory
from app.models.stage_instance import StageInstance
from app.services.file_storage import resolve_document_path, resolve_resume_path
from app.services.job_descriptions import version_file_paths

logger = logging.getLogger(__name__)

__all__ = ["delete_requisition_cascade", "remove_orphaned_files"]


def _uploaded_file_paths(db: Session, application_ids: list[int]) -> list[Path]:
    """On-disk paths of the resumes and supplemental documents belonging
    to these applications.

    Read before the rows are deleted, and only returned, so unlinking can
    wait for the commit.
    """
    if not application_ids:
        return []

    resumes = db.scalars(
        select(ApplicationResume.stored_path).where(
            ApplicationResume.application_id.in_(application_ids)
        )
    )
    documents = db.scalars(
        select(ApplicationDocument.stored_path).where(
            ApplicationDocument.application_id.in_(application_ids)
        )
    )
    return [resolve_resume_path(p) for p in resumes if p] + [
        resolve_document_path(p) for p in documents if p
    ]


def remove_orphaned_files(paths: list[Path]) -> None:
    """Unlinks the files a committed delete left behind.

    Called *after* the commit: a rolled-back transaction must never have
    lost its files. Best-effort: a file already gone, or not removable, is
    logged and skipped. These are people's resumes, so they must not
    outlive their records.
    """
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove uploaded file %s", path, exc_info=True)


def delete_requisition_cascade(db: Session, requisition: JobRequisition) -> list[Path]:
    """Removes the requisition and every row that depends on it, and
    returns the uploaded files now orphaned by it.

    Deletes run leaves-first, since every child must go before its parent:

        job_requisitions
        |-- job_description_versions      (+ their PDFs on disk)
        |-- requisition_evaluators
        |-- exam_slots
        |     `-- exam_slot_bookings          (exam_slot_id)
        `-- candidate_applications
              |-- agent_runs
              |-- application_documents
              |-- application_resumes
              |-- stage_history
              |-- notifications               (application_id nulled, kept)
              |-- exam_slot_bookings          (application_id)
              `-- stage_instances
                    |-- exam_slot_bookings    (stage_instance_id)
                    |-- interview_availability
                    `-- interview_reschedule_requests

    Deliberately not `ondelete="CASCADE"` in the schema, which would fire
    from any stray delete; this explicit call sits behind the guard in
    api/hr/requisitions. Does NOT commit or touch the filesystem: the
    caller commits, then passes the returned paths to
    remove_orphaned_files.
    """
    application_ids = list(
        db.scalars(
            select(CandidateApplication.id).where(
                CandidateApplication.requisition_id == requisition.id
            )
        )
    )
    orphaned_files = _uploaded_file_paths(db, application_ids) + version_file_paths(db, requisition.id)

    if application_ids:
        stage_instance_ids = list(
            db.scalars(
                select(StageInstance.id).where(StageInstance.application_id.in_(application_ids))
            )
        )
        if stage_instance_ids:
            db.execute(
                delete(InterviewRescheduleRequest).where(
                    InterviewRescheduleRequest.stage_instance_id.in_(stage_instance_ids)
                )
            )
            db.execute(
                delete(InterviewAvailability).where(
                    InterviewAvailability.stage_instance_id.in_(stage_instance_ids)
                )
            )
        # Every booking carries an application_id, so this one statement
        # clears the exam_slot_id and stage_instance_id paths too.
        db.execute(
            delete(ExamSlotBooking).where(ExamSlotBooking.application_id.in_(application_ids))
        )
        db.execute(delete(StageInstance).where(StageInstance.application_id.in_(application_ids)))
        db.execute(delete(AgentRun).where(AgentRun.application_id.in_(application_ids)))
        db.execute(
            delete(ApplicationDocument).where(
                ApplicationDocument.application_id.in_(application_ids)
            )
        )
        db.execute(
            delete(ApplicationResume).where(ApplicationResume.application_id.in_(application_ids))
        )
        db.execute(delete(StageHistory).where(StageHistory.application_id.in_(application_ids)))
        # Notices about these applications stay in people's inboxes --
        # they happened -- but let go of the application, which is how
        # the reading pane knows to say "no longer available".
        db.execute(
            update(Notification)
            .where(Notification.application_id.in_(application_ids))
            .values(application_id=None)
        )
        db.execute(
            delete(CandidateApplication).where(
                CandidateApplication.requisition_id == requisition.id
            )
        )

    # A booking whose application is already gone can't exist, but a slot
    # provisioned and never booked can -- and it still blocks its own row.
    slot_ids = list(db.scalars(select(ExamSlot.id).where(ExamSlot.requisition_id == requisition.id)))
    if slot_ids:
        db.execute(delete(ExamSlotBooking).where(ExamSlotBooking.exam_slot_id.in_(slot_ids)))
    db.execute(delete(ExamSlot).where(ExamSlot.requisition_id == requisition.id))
    db.execute(
        delete(RequisitionEvaluator).where(RequisitionEvaluator.requisition_id == requisition.id)
    )
    db.execute(
        delete(JobDescriptionVersion).where(JobDescriptionVersion.requisition_id == requisition.id)
    )
    db.delete(requisition)

    return orphaned_files
