"""Whether an authored workflow is *sensible*: the DFA accepts any
authored order, so this is the separate check (validate_workflow).
"""

from dataclasses import dataclass
from typing import Literal

from app.domain.dfa import is_exam_stage, is_interview_stage

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class WorkflowIssue:
    severity: Severity
    code: str
    message: str


# these have one label regardless of job (unlike interview_round_k
# / examination_k, which carry per-job names) — safe to hardcode, keeps
# messages readable without a requisition in scope
_DOC = "Document Upload"
_SKILL = "Pre-Screening"
_SHORTLIST = "Shortlisting"
_FINAL = "Final Decision"
_ONBOARD = "Onboarding"

# retired -- still StageType values (stage_history records
# moves through them), but no workflow may use them again
_RETIRED_STAGES = ("reference_check", "background_check")


def validate_workflow(stages: list[str]) -> list[WorkflowIssue]:
    """Every issue with this stage list, worst first. Shared by the save and
    the Workflow Builder's live checklist, so they never disagree.

    - **error** (E0-E5): the app depends on the order, or it would produce
      a wrong record (deciding before interviewing). Saving is refused.
      Document Upload, Shortlisting, Final Decision, Onboarding and at
      least one interview round are required.
    - **warning**: runnable but probably unintended (no Pre-Screening
      means no pre-screening questions). Never blocks: HR may mean it.

    The caller (update_requisition_workflow) runs this only when the
    stage order changes, so a label-only edit is never refused. Assumes
    valid StageType values.
    """
    issues: list[WorkflowIssue] = []

    def error(code: str, message: str) -> None:
        issues.append(WorkflowIssue("error", code, message))

    def warning(code: str, message: str) -> None:
        issues.append(WorkflowIssue("warning", code, message))

    # E0 -- no duplicates (also checked by the schema; same message).
    # returns early: the position checks mean nothing with a repeat
    if len(set(stages)) != len(stages):
        error("duplicate_stage", "Each stage may only appear once in a workflow.")
        return issues

    # E0b -- no retired stages. Nothing on the profile records a result
    # for them any more, so a job using one would park candidates on a
    # stage nobody can act on.
    if any(stage in _RETIRED_STAGES for stage in stages):
        error("retired_stage", "Reference and background checks are no longer part of ARKIVE.")

    # E1 -- Document Upload must be first: current_stage starts at
    # workflow[0], and the applicant's first act is the upload
    if "document_upload" not in stages:
        error("document_upload_first", f"A workflow must start with {_DOC}, where every application begins.")
    elif stages[0] != "document_upload":
        error("document_upload_first", f"{_DOC} must be the first stage, since every application begins there.")

    # E2 -- Pre-Screening, if used, immediately after Document Upload.
    # The resume match itself runs at upload; Pre-Screening is the
    # question set, and its answers belong in front of every human stage.
    # The message only states the rule; it must not claim Pre-Screening
    # screens the uploaded application, which it does not.
    # (absent is just a warning, not this)
    if "skill_matching" in stages:
        if stages.index("skill_matching") != 1:
            error(
                "skill_matching_position",
                f"{_SKILL} must come immediately after {_DOC}.",
            )
    else:
        warning(
            "no_skill_matching",
            f"No {_SKILL}: candidates won't be asked any pre-screening questions.",
        )

    # E5 -- Shortlisting is required, before every interview round
    # (interviews are only for shortlisted candidates). An exam may come
    # before it.
    if "shortlisting" not in stages:
        error("shortlisting_required", f"{_SHORTLIST} can't be removed. Every workflow needs it.")
    else:
        before = stages[: stages.index("shortlisting")]
        if any(is_interview_stage(s) for s in before):
            error(
                "shortlisting_before_interviews",
                f"{_SHORTLIST} must come before every interview round.",
            )

    # E6 -- at least one interview round. Every hire is interviewed at
    # least once, so a workflow without one can't be saved or published
    if not any(is_interview_stage(s) for s in stages):
        error("interview_required", "A workflow needs at least one interview round.")

    # E3 -- Onboarding is required, and last -- it's the post-hire step,
    # anything after it runs on someone already onboarded. Required
    # because the hire and offer steps hand the candidate to it
    if "onboarding" not in stages:
        error("onboarding_required", f"{_ONBOARD} can't be removed. Every workflow ends with it.")
    elif stages[-1] != "onboarding":
        error("onboarding_last", f"{_ONBOARD} must be the last stage. It is what happens after a candidate is hired.")

    # E4 -- Final Decision is required (the hire decision is recorded
    # there), after every interview and exam, the evidence it weighs
    if "final_decision" in stages:
        after = stages[stages.index("final_decision") + 1 :]
        if any(is_interview_stage(s) or is_exam_stage(s) for s in after):
            error(
                "final_decision_after_evaluations",
                f"{_FINAL} must come after every interview and examination stage, since those are the evidence it weighs.",
            )
    else:
        error("final_decision_required", f"{_FINAL} can't be removed. Every workflow needs it.")

    return issues


def workflow_errors(stages: list[str]) -> list[str]:
    """Just the blocking messages, for the save path to refuse with."""
    return [issue.message for issue in validate_workflow(stages) if issue.severity == "error"]
