import enum


class UserRole(str, enum.Enum):
    applicant = "applicant"
    hr_admin = "hr_admin"
    evaluator = "evaluator"


class RequisitionStatus(str, enum.Enum):
    draft = "draft"
    open = "open"
    closed = "closed"


class StageType(str, enum.Enum):
    """Locked vocabulary: every workflow is authored against it, so a
    change is a migration.

    Legacy values stay because Postgres cannot drop enum values and old
    records use them: interview_hr_director/dept_head/vp (use
    interview_round_1..6), `examination` (use examination_1..4), and the
    retired reference_check/background_check, which workflow_rules
    refuses."""

    document_upload = "document_upload"
    skill_matching = "skill_matching"
    shortlisting = "shortlisting"
    examination = "examination"
    examination_1 = "examination_1"
    examination_2 = "examination_2"
    examination_3 = "examination_3"
    examination_4 = "examination_4"
    interview_hr_director = "interview_hr_director"
    interview_dept_head = "interview_dept_head"
    interview_vp = "interview_vp"
    interview_round_1 = "interview_round_1"
    interview_round_2 = "interview_round_2"
    interview_round_3 = "interview_round_3"
    interview_round_4 = "interview_round_4"
    interview_round_5 = "interview_round_5"
    interview_round_6 = "interview_round_6"
    reference_check = "reference_check"
    background_check = "background_check"
    final_decision = "final_decision"
    onboarding = "onboarding"


class StageStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    complete = "complete"
    skipped = "skipped"


class ApplicationStatus(str, enum.Enum):
    """Hire/reject outcome, deliberately decoupled from the DFA: HR can
    set it at any stage.

    `flagged` (a weak Skill Matching fit) is NOT an auto-rejection: the
    application is frozen at skill_matching until HR resolves it (POST
    /hr/applications/{id}/resolve-flag)."""

    active = "active"
    rejected = "rejected"
    hired = "hired"
    flagged = "flagged"
    # applicant-initiated ("Cancel Application") — distinct from
    # `rejected` (an HR decision) so the two read differently wherever
    # status is surfaced. freezes the DFA, same as `flagged`.
    withdrawn = "withdrawn"


class RescheduleRequestStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    denied = "denied"


class ExamBookingStatus(str, enum.Enum):
    """Separate enum from RescheduleRequestStatus despite identical
    values -- semantically distinct entities (an initial proposal vs. a
    reschedule of an already-confirmed one), and this codebase forks
    status enums per use case rather than reusing one across unrelated
    tables."""

    pending = "pending"
    approved = "approved"
    denied = "denied"
