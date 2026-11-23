"""Seed demo JobRequisitions + CandidateApplications.

Two jobs with deliberately different workflow_definitions -- this is
what proves the DFA is generated per job rather than hand-maintained as
one fixed shape. Each demo application is created via
create_application_with_stage_instances, so its StageInstance rows are
already pre-generated the way a real application's would be.

Safe to re-run: an existing job (by title) or application (by
applicant+requisition pair) is left untouched rather than duplicated.

Usage (from backend/, with the venv active, after seed_demo_users.py):
    python -m scripts.seed_demo_pipeline
"""

from sqlalchemy import select

from app.infra.db import SessionLocal
from app.models.enums import RequisitionStatus
from app.models.job_requisition import JobRequisition
from app.models.user import User
from app.models.candidate_application import CandidateApplication
from app.services.applications import create_application_with_stage_instances

# uses the generic interview_round_k slots, matching what
# _WORKFLOW_PRESETS gives every job created through the UI, so a fresh
# environment seeds jobs in the shape new jobs have.
# interview_round_labels supplies the human-facing names.
DEMO_JOBS = [
    dict(
        title="Software Engineer I",
        department="Computing",
        workflow_definition=[
            "document_upload",
            "skill_matching",
            "shortlisting",
            "examination",
            "interview_round_1",
            "interview_round_2",
            "interview_round_3",
            "final_decision",
            "onboarding",
        ],
        interview_round_labels={
            "interview_round_1": "HR Interview",
            "interview_round_2": "Department Head Interview",
            "interview_round_3": "VP Interview",
        },
    ),
    dict(
        title="Library Assistant (Part-Time)",
        department="Library Services",
        # Deliberately shorter — no skill matching, no exam, no third
        # round. Proves the DFA generator adapts per job instead of
        # assuming a fixed global sequence.
        workflow_definition=[
            "document_upload",
            "interview_round_1",
            "interview_round_2",
            "final_decision",
            "onboarding",
        ],
        interview_round_labels={
            "interview_round_1": "HR Interview",
            "interview_round_2": "Department Head Interview",
        },
    ),
]


def seed() -> None:
    db = SessionLocal()
    try:
        hr_admin = db.scalar(select(User).where(User.email == "hr@arkive.demo"))
        applicant = db.scalar(select(User).where(User.email == "applicant@arkive.demo"))
        if hr_admin is None or applicant is None:
            raise RuntimeError(
                "Demo users not found — run `python -m scripts.seed_demo_users` first."
            )

        requisitions: list[JobRequisition] = []
        for spec in DEMO_JOBS:
            existing = db.scalar(
                select(JobRequisition).where(JobRequisition.title == spec["title"])
            )
            if existing is not None:
                print(f"skip (already exists): job '{spec['title']}'")
                requisitions.append(existing)
                continue

            job = JobRequisition(
                title=spec["title"],
                department=spec["department"],
                status=RequisitionStatus.open,
                workflow_definition=spec["workflow_definition"],
                interview_round_labels=spec["interview_round_labels"],
                created_by=hr_admin.id,
            )
            db.add(job)
            db.flush()
            print(f"created: job '{job.title}' ({len(job.workflow_definition)} stages)")
            requisitions.append(job)

        for job in requisitions:
            existing_application = db.scalar(
                select(CandidateApplication).where(
                    CandidateApplication.applicant_id == applicant.id,
                    CandidateApplication.requisition_id == job.id,
                )
            )
            if existing_application is not None:
                print(f"skip (already exists): application for '{job.title}'")
                continue

            application = create_application_with_stage_instances(
                db, applicant_id=applicant.id, requisition=job
            )
            print(
                f"created: application #{application.id} for '{job.title}' "
                f"(current_stage={application.current_stage})"
            )

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
