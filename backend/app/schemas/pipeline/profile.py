"""What HR reads about candidates: the Candidate Profile, the Final
Decision Board and the Pre-201 package.
"""

from datetime import datetime

from pydantic import BaseModel

from app.domain.scorecard import GeneralEvaluationTier
from app.models.enums import ApplicationStatus, StageType
from app.schemas.application_document import ApplicationDocumentRead
from app.schemas.hire_decision import DecisionRecordRead
from app.schemas.resume import ApplicationResumeRead
from app.schemas.skill_match import RequisitionMatch
from app.schemas.synthesis import CandidateSynthesis


class PreScreeningQAEntry(BaseModel):
    """One pre-screening question and the applicant's answer. The text
    comes from the job, the answer from the skill_matching payload;
    question_text falls back to the id if HR deleted the question."""

    question_id: str
    question_text: str
    answer: str


class CandidateProfile(BaseModel):
    """Backs the HR "Candidate Profile Synthesis" screen. match_score/
    top_skills/evaluation_summary/strength_tags/match_gaps are real
    Skill Matching output once the candidate has reached skill_matching;
    next_steps and stage data are derived from the DFA."""

    application_id: int
    requisition_id: int
    applicant_name: str
    applicant_avatar_url: str | None = None
    job_title: str
    current_stage: StageType | None
    current_stage_label: str | None
    status: ApplicationStatus
    # None until the applicant has submitted the document_upload stage.
    resume: ApplicationResumeRead | None
    # free text captured alongside the resume at document_upload
    # (optional, applicant's own words), not a separate PDF upload. None
    # if left blank or not reached yet.
    letter_of_intent: str | None
    # supplemental documents the applicant added after their initial
    # document_upload submission
    documents: list[ApplicationDocumentRead] = []
    match_score: float | None
    match_semantic_score: float | None
    match_keyword_score: float | None
    top_skills: list[str]
    # a single fixed stage, but dict-keyed like interview_ratings/
    # examinations below: 0 or 1 entries depending on whether this job's
    # workflow uses it at all.
    shortlisting: dict[str, dict]
    # keyed by whichever interview_* stage types this job's workflow
    # uses, in workflow order. item_ratings/computed_score/tier/remarks/
    # submitted_by/submitted_at are None until the assigned evaluator
    # actually submits. schedule is HR-set, independent of submission.
    interview_ratings: dict[str, dict]
    # equal-weighted average of each evaluated round's computed_score.
    # None until at least one round has a submitted evaluation. computed
    # fresh on every read, not persisted.
    evaluator_consensus_score: float | None
    # keyed by whichever examination_* stage types this job's workflow
    # uses, in workflow order -- mirrors interview_ratings' shape.
    # included even while `pending` so a pending exam-slot booking
    # proposal is visible to HR before the applicant gets there.
    examinations: dict[str, dict]
    evaluation_summary: str | None
    strength_tags: list[str]
    match_gaps: list[str]
    # Interview Analysis Agent output -- a grounded read of the AI
    # Pre-Screening answers, distinct from Skill Matching's resume-vs-JD
    # analysis above. empty until the candidate submits pre-screening
    # for a job with at least one question.
    pre_screening_qa: list[PreScreeningQAEntry]
    interview_analysis_summary: str | None
    interview_analysis_strengths: list[str]
    interview_analysis_gaps: list[str]
    # Decision Support inputs (C4, C2) -- None until their respective
    # inputs exist, same "computed fresh on every read" convention as
    # evaluator_consensus_score above
    interview_rubric_score: float | None
    exam_percentile: float | None
    # aggregate Highly-Qualified/Qualified/Not-Qualified read against
    # evaluator_consensus_score -- distinct from each round's own
    # per-round tier inside interview_ratings above
    overall_tier: GeneralEvaluationTier | None
    # WSM output -- only non-None once match_score, exam_percentile,
    # evaluator_consensus_score, and interview_rubric_score are all
    # available; the formula can't run on partial inputs
    final_synthesis_score: float | None
    # true when status == "flagged" -- a review gate, never an
    # auto-rejection (POST /hr/applications/{id}/resolve-flag). The
    # skill_matching payload's `flag_reason` says why.
    flagged: bool
    suggested_requisitions: list[RequisitionMatch]
    # same value and null-when-flagged rule as ApplicationListItem.
    # next_stage: the target the profile's Advance button names
    next_stage: StageType | None
    next_stage_label: str | None
    next_steps: str
    # per-criterion breakdown of the WSM (available / not yet recorded /
    # cannot be produced), agent coverage and the AgentRun trail
    synthesis: CandidateSynthesis
    # who decided, when, from which stage, why, and whether an incomplete
    # record was acknowledged. None if not decided (or decided before
    # decisions were recorded).
    decision: DecisionRecordRead | None


class FinalDecisionBoardEntry(BaseModel):
    """One candidate's row on the Final Decision Board -- every score
    that feeds into the ranking, laid bare for the HR Director's final
    call. Purely informational; no hire/reject action lives here."""

    application_id: int
    applicant_name: str
    hr_score: float
    dept_score: float
    vp_score: float
    skill_match_score: float | None
    exam_percentile: float | None
    interview_rubric_score: float | None
    executive_consensus_score: float
    final_synthesis_score: float | None
    overall_tier: GeneralEvaluationTier


class FinalDecisionBoardResponse(BaseModel):
    requisition_id: int
    job_title: str
    # sorted descending by (vp_score, dept_score, hr_score,
    # skill_match_score) -- only candidates whose job uses the fixed
    # 3-role executive shape, all three submitted, appear here at all
    entries: list[FinalDecisionBoardEntry]


class Pre201Package(BaseModel):
    """The Pre-201 package: a read-only bundle of a hired applicant's full
    record, built on read from the same data as build_candidate_profile
    (not stored). Only for applications with status == hired."""

    application_id: int
    applicant_name: str
    applicant_email: str
    job_title: str
    # approximated as CandidateApplication.updated_at (there is no
    # hired_at column): the last time the row changed
    hired_at: datetime
    resume: ApplicationResumeRead | None
    letter_of_intent: str | None
    shortlisting: dict[str, dict]
    examinations: dict[str, dict]
    interview_ratings: dict[str, dict]
    match_score: float | None
    evaluator_consensus_score: float | None
    interview_rubric_score: float | None
    exam_percentile: float | None
    overall_tier: GeneralEvaluationTier | None
    final_synthesis_score: float | None
    # the Candidate Profile's synthesis, kept in the permanent record
    synthesis: CandidateSynthesis
    # who authorised this hire and on what basis
    decision: DecisionRecordRead | None
