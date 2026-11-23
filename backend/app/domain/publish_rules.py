"""What a job opening needs before it can be published (publish_blockers).
Pure.
"""

from datetime import date

from app.domain.workflow_rules import workflow_errors


def publish_blockers(
    *,
    application_deadline: date | None,
    workflow_definition: list[str],
    pre_screening_questions: list[dict] | None,
) -> list[str]:
    """Every reason this job can't be published yet, in the order HR
    would fix them; empty when it can. The panel's requirement: every
    prerequisite, such as the pre-screening questions, complete before
    publishing. A draft may be incomplete; this runs on create-with-publish
    and when a draft is published (api/hr/requisitions.py)."""
    blockers: list[str] = []
    if application_deadline is None:
        blockers.append("Set an application deadline.")
    blockers.extend(workflow_errors(workflow_definition))
    if "skill_matching" in workflow_definition and not pre_screening_questions:
        blockers.append("Add at least one pre-screening question. This job's workflow includes Pre-Screening.")
    return blockers
