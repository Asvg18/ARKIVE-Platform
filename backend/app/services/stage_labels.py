"""Stage display labels, resolved on the server because round and exam
labels are per-job data most screens have no job in scope to look up.
"""

from app.domain.dfa import InvalidTransitionError
from app.models.job_requisition import JobRequisition

_DEFAULT_LABELS: dict[str, str] = {
    "document_upload": "Document Upload",
    "skill_matching": "Pre-Screening",
    "shortlisting": "Shortlisting",
    "examination": "Examination",
    # the first exam is just "Examination"
    "examination_1": "Examination",
    "examination_2": "Examination 2",
    "examination_3": "Examination 3",
    "examination_4": "Examination 4",
    "interview_hr_director": "HR Administrator Interview",
    "interview_dept_head": "Department Head Interview",
    "interview_vp": "VP Interview",
    "interview_round_1": "Interview Round 1",
    "interview_round_2": "Interview Round 2",
    "interview_round_3": "Interview Round 3",
    "interview_round_4": "Interview Round 4",
    "interview_round_5": "Interview Round 5",
    "interview_round_6": "Interview Round 6",
    "reference_check": "Reference Check",
    "background_check": "Background Check",
    "final_decision": "Final Decision",
    "onboarding": "Onboarding",
}


def resolve_stage_label(stage_type: str | None, requisition: JobRequisition | None) -> str:
    """The label HR actually gave this stage for this specific job, if
    any (interview_round_k or examination_k slots only), else a sensible
    default, else the raw stage_type string as a last resort."""
    if stage_type is None:
        return "–"
    override = None
    if requisition:
        override = (requisition.interview_round_labels or {}).get(stage_type) or (
            requisition.examination_labels or {}
        ).get(stage_type)
    return override or _DEFAULT_LABELS.get(stage_type, stage_type)


def describe_transition_error(
    error: InvalidTransitionError, requisition: JobRequisition | None
) -> str:
    """The automaton's rejection, in the stage names HR gave this job.

    dfa.py raises with raw stage keys; this names them as the job does.
    Falls back to the raw reason when there is no expected stage.
    """
    if error.expected_stage is None or error.current_stage is None:
        return error.reason
    return (
        f"{resolve_stage_label(error.target_stage, requisition)} is not the next step. "
        f"After {resolve_stage_label(error.current_stage, requisition)}, this job's "
        f"workflow goes to {resolve_stage_label(error.expected_stage, requisition)}."
    )
