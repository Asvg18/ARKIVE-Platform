/** What HR reads about one candidate: the Candidate Profile, the decision
 *  record, the Final Decision Board and the Pre-201 package. */

import type { GeneralEvaluationTier } from "../../lib/scorecard";
import type { ApplicationDocument } from "../applicationDocument";
import type { ApplicationResumeRead } from "../resume";
import type { RequisitionMatch } from "../skillMatch";
import type { ApplicationStatus, StageType } from "./applications";
import type { InterviewRatingEntry } from "./interviews";
import type { ExaminationEntry } from "./exams";
import type { CandidateSynthesis } from "./synthesis";

export interface FinalDecisionBoardEntry {
  application_id: number;
  applicant_name: string;
  hr_score: number;
  dept_score: number;
  vp_score: number;
  skill_match_score: number | null;
  exam_percentile: number | null;
  interview_rubric_score: number | null;
  executive_consensus_score: number;
  final_synthesis_score: number | null;
  overall_tier: GeneralEvaluationTier;
}

export interface FinalDecisionBoardResponse {
  requisition_id: number;
  job_title: string;
  entries: FinalDecisionBoardEntry[];
}

export interface ShortlistingEntry {
  label: string;
  status: string;
  outcome: "shortlisted" | "not_shortlisted" | null;
  notes: string | null;
}

export interface PreScreeningQAEntry {
  question_id: string;
  question_text: string;
  answer: string;
}

export interface CandidateProfile {
  application_id: number;
  requisition_id: number;
  applicant_name: string;
  /** Their profile photo (render through Avatar); null = initials. */
  applicant_avatar_url?: string | null;
  job_title: string;
  current_stage: StageType | null;
  current_stage_label: string | null;
  status: ApplicationStatus;
  resume: ApplicationResumeRead | null;
  letter_of_intent: string | null;
  documents: ApplicationDocument[];
  match_score: number | null;
  match_semantic_score: number | null;
  match_keyword_score: number | null;
  top_skills: string[];
  shortlisting: Record<string, ShortlistingEntry>;
  interview_ratings: Record<string, InterviewRatingEntry>;
  evaluator_consensus_score: number | null;
  examinations: Record<string, ExaminationEntry>;
  evaluation_summary: string | null;
  strength_tags: string[];
  match_gaps: string[];
  pre_screening_qa: PreScreeningQAEntry[];
  interview_analysis_summary: string | null;
  interview_analysis_strengths: string[];
  interview_analysis_gaps: string[];
  interview_rubric_score: number | null;
  exam_percentile: number | null;
  overall_tier: GeneralEvaluationTier | null;
  final_synthesis_score: number | null;
  flagged: boolean;
  suggested_requisitions: RequisitionMatch[];
  /** Where the DFA says this candidate goes next -- so the profile can
   *  offer the same "Advance" the pipeline list does, instead of
   *  sending HR back to find them there. Null at the terminal stage,
   *  and null while flagged (the DFA is frozen until resolved). */
  next_stage: StageType | null;
  next_stage_label: string | null;
  next_steps: string;
  synthesis: CandidateSynthesis;
  decision: DecisionRecord | null;
}

/**
 * One reason a candidate's record is not complete enough to close.
 * Carries a human sentence rather than a code — rendered verbatim in the
 * hire confirmation dialog and stored verbatim in the decision record,
 * so a reader of an old record sees exactly what the decider was shown.
 */
export interface DecisionBlocker {
  /** "check_outcome" came from the retired reference/background checks
   * — nothing raises it now, but older decision records store it and
   * still read back. "shortlisting_outcome" is the
   * Shortlisting stage, which also sits outside the WSM. */
  key: "stage" | "interview_round" | "criterion" | "check_outcome" | "shortlisting_outcome";
  label: string;
  detail: string;
}

/**
 * The 409 body PATCH .../status returns when the hire gate stops a
 * decision. `incomplete_record` means the record is not complete and the
 * caller has not acknowledged that; `reason_required` means they
 * acknowledged it but gave no reason — overriding the gate silently
 * would leave the record no better off than before the gate existed.
 */
export interface IncompleteRecordDetail {
  code: "incomplete_record" | "reason_required";
  message: string;
  blockers: DecisionBlocker[];
}

/**
 * The hire/reject decision itself, once one has been made. Null for an
 * application nobody has closed, and also null for every application
 * closed before decisions were recorded at all (applications 3 and 100).
 */
export interface DecisionRecord {
  status: string;
  previous_status: string;
  reason: string | null;
  /** True means HR was shown the outstanding items and closed anyway. */
  acknowledged_incomplete: boolean;
  decided_by_name: string | null;
  decided_at: string;
  /** Where the candidate stood when this was decided. */
  decided_at_stage_label: string | null;
  blockers: DecisionBlocker[];
  final_synthesis_score: number | null;
  overall_tier: GeneralEvaluationTier | null;
}

export interface Pre201Package {
  application_id: number;
  applicant_name: string;
  applicant_email: string;
  job_title: string;
  // decision record's own timestamp when there is one; falls back to
  // the application's last-updated time for applications closed before
  // decisions were recorded
  hired_at: string;
  resume: ApplicationResumeRead | null;
  letter_of_intent: string | null;
  shortlisting: Record<string, ShortlistingEntry>;
  examinations: Record<string, ExaminationEntry>;
  interview_ratings: Record<string, InterviewRatingEntry>;
  match_score: number | null;
  evaluator_consensus_score: number | null;
  interview_rubric_score: number | null;
  exam_percentile: number | null;
  overall_tier: GeneralEvaluationTier | null;
  final_synthesis_score: number | null;
  synthesis: CandidateSynthesis;
  decision: DecisionRecord | null;
}
