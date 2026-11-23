/** Applications as HR's lists and actions see them, and the stage and
 *  status vocabulary. */


// interview_hr_director/dept_head/vp are legacy, superseded by the
// generic interview_round_1..6 slots -- kept only so already-in-flight
// applications on those stages still type-check
export type StageType =
  | "document_upload"
  | "skill_matching"
  | "shortlisting"
  | "examination"
  | "examination_1"
  | "examination_2"
  | "examination_3"
  | "examination_4"
  | "interview_hr_director"
  | "interview_dept_head"
  | "interview_vp"
  | "interview_round_1"
  | "interview_round_2"
  | "interview_round_3"
  | "interview_round_4"
  | "interview_round_5"
  | "interview_round_6"
  // retired; still backend enum values, for stage history
  | "reference_check"
  | "background_check"
  | "final_decision"
  | "onboarding";

export type ApplicationStatus = "active" | "rejected" | "hired" | "flagged" | "withdrawn";

export interface ApplicationListItem {
  id: number;
  applicant_name: string;
  /** Their profile photo (render through Avatar); null = initials. */
  applicant_avatar_url?: string | null;
  job_title: string;
  /** Which job this belongs to — the board groups by it, since each job
   * runs its own workflow and so has its own set of columns. */
  requisition_id: number;
  current_stage: StageType | null;
  current_stage_label: string | null;
  next_stage: StageType | null;
  status: ApplicationStatus;
  match_score: number | null;
  /** The shortlisting call on record, if any — so the bulk-shortlist
   *  preview can show a decision that already exists rather than
   *  previewing a split that contradicts the candidate's own profile. */
  shortlisting_outcome: string | null;
}

export interface TransitionResponse {
  application_id: number;
  previous_stage: StageType | null;
  current_stage: StageType;
}

export interface ResolveFlagRequest {
  decision: "continue" | "reject";
}

/** One row of a bulk-shortlist result — what actually happened to this
 *  candidate, including whether the letter reached them, which is the
 *  half of the operation that can fail quietly. */
export interface ShortlistedCandidate {
  application_id: number;
  applicant_name: string;
  /** null for a candidate who had no score to rank. */
  rank: number | null;
  match_score: number | null;
  outcome: string;
  emailed: boolean;
}

export interface ShortlistResult {
  shortlisted: ShortlistedCandidate[];
  not_shortlisted: ShortlistedCandidate[];
  /** Decided already, on the candidate's own profile, so not part of
   *  this action — reported so the numbers add up rather than a name
   *  quietly going missing. */
  already_decided: ShortlistedCandidate[];
  emails_failed: number;
}
