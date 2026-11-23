import type { ApplicationDocument } from "./applicationDocument";
import type { ApplicationStatus } from "./pipeline";
import type { ApplicationResumeRead } from "./resume";

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
  | "reference_check"
  | "background_check"
  | "final_decision"
  | "onboarding";

export type StageInstanceStatus = "pending" | "in_progress" | "complete" | "skipped";

export interface StageInstance {
  stage_type: StageType;
  // HR's real per-job label for this stage (e.g. "Technical Exam"),
  // resolved server-side — prefer this over the static stageLabel()
  // fallback wherever it's available.
  label: string;
  status: StageInstanceStatus;
  payload: Record<string, unknown> | null;
  completed_at: string | null;
}

export interface PreScreeningQuestion {
  id: string;
  text: string;
  required: boolean;
}

/** One exam session the applicant can still book: not started, with a
 *  seat left. `end_time` is null on sessions made before they had one. */
/** The exam session the applicant is booked in, and whether they can
 *  still change it themselves (until 24 hours before it starts). */
export interface ExamBookingSummary {
  stage_type: StageType;
  slot_id: number;
  date: string;
  time: string;
  end_time: string | null;
  location: string;
  can_change: boolean;
}

export interface ExamSlotOption {
  id: number;
  date: string;
  time: string;
  end_time: string | null;
  location: string;
  remaining_capacity: number;
}

/** The interview times HR sent for the round the applicant is on, while
 *  it isn't booked. `slots` is only what's still free; `response` is
 *  "none_work" once they've told HR none suit. */
export interface InterviewSlotOffer {
  stage_type: StageType;
  duration_minutes: number;
  mode: "in_person" | "online";
  location: string | null;
  slots: { date: string; time: string; end_time: string }[];
  response: "none_work" | null;
  note: string | null;
}

export interface ApplicantExamResult {
  label: string;
  score: number;
}

export interface Offer {
  deadline: string;
  window_days: number;
  /** accepted | declined | expired, or null while the window is still open
   * and unanswered. "expired" is written by the backend's lazy expiry
   * check, never by the applicant. */
  response: "accepted" | "declined" | "expired" | null;
  responded_at: string | null;
}

/** The applicant's answer to "can you make this time?", carried on a
 *  scheduled interview stage's own payload. null `response` means it is
 *  still theirs to answer; the whole block is absent on a stage that
 *  isn't scheduled, or that was scheduled before this existed. */
export interface ScheduleConfirmation {
  response: "confirmed" | "unavailable" | null;
  asked_at: string | null;
  responded_at: string | null;
  note: string | null;
}

export interface ShortlistingAcceptance {
  /** null while it is still theirs to answer. */
  response: "accepted" | "declined" | null;
  opened_at: string | null;
  responded_at: string | null;
}

export interface ApplicationDetail {
  id: number;
  /** The job applied to — marks it "Applied" in the job browser. */
  requisition_id: number;
  job_title: string;
  job_department: string;
  current_stage: StageType | null;
  status: ApplicationStatus;
  stage_instances: StageInstance[];
  resume: ApplicationResumeRead | null;
  // always populated (the question text itself was never sensitive) --
  // pairs with the raw answers living in the skill_matching
  // StageInstance's own payload, which Review My Submission reads
  // regardless of current stage
  pre_screening_questions: PreScreeningQuestion[];
  // the sessions they can book for the exam stage they are on, only
  // while it is unscheduled -- empty everywhere else
  exam_sessions: ExamSlotOption[];
  /** The session they're booked in for the exam they're on. */
  exam_booking: ExamBookingSummary | null;
  /** Set once they've said none of the open sessions work. */
  exam_none_work: { note: string | null; at: string } | null;
  interview_slot_offer: InterviewSlotOffer | null;
  // only populated once HR has recorded at least one exam score
  examination_results: Record<string, ApplicantExamResult>;
  exam_percentile: number | null;
  // supplemental files added after the initial document_upload
  // submission -- distinct from `resume` above
  documents: ApplicationDocument[];
  // null for a legacy hire that predates offers -- the UI must treat
  // "hired with no offer" as a valid state
  offer: Offer | null;
  // The confirmation a shortlisted candidate owes before an examination
  // is booked in their name. null when there is nothing to answer: not
  // shortlisted, no shortlisting stage in this job, or shortlisted
  // before this existed — in which case the stage advances as it always
  // did and the applicant is never shown a decision to make.
  shortlisting_acceptance: ShortlistingAcceptance | null;
}

export interface PreScreeningAnswer {
  question_id: string;
  value: string;
}

export interface PreScreeningSubmission {
  answers: PreScreeningAnswer[];
}
