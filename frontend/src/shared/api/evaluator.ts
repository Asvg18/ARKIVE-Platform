import type { EvaluatorRecommendation, GeneralEvaluationTier } from "../lib/scorecard";
import type { ApplicationResumeRead } from "./resume";

export interface InterviewListItem {
  stage_instance_id: number;
  application_id: number;
  applicant_name: string;
  applicant_avatar_url?: string | null;
  job_title: string;
  stage_label: string;
  status: string;
  already_evaluated: boolean;
  /** The applicant has confirmed the interview time; the form stays
   *  locked until then. */
  schedule_confirmed: boolean;
}

export interface EvaluationRecord {
  item_ratings: Record<string, number | null>;
  computed_score: number;
  tier: GeneralEvaluationTier;
  /** Null only for evaluations submitted before this field existed. */
  recommendation: EvaluatorRecommendation | null;
  remarks: string;
  ai_summary: string;
  submitted_by: number;
  submitted_at: string;
}

export interface EvaluateRequestBody {
  item_ratings: Record<string, number | null>;
  remarks: string;
  recommendation: EvaluatorRecommendation;
}

export interface RescheduleRequest {
  id: number;
  proposed_date: string;
  proposed_time: string;
  reason: string | null;
  status: string;
  created_at: string;
}

export interface RescheduleRequestCreate {
  proposed_date: string;
  proposed_time: string;
  reason?: string | null;
}

export interface InterviewDetail {
  stage_instance_id: number;
  application_id: number;
  applicant_name: string;
  applicant_avatar_url?: string | null;
  job_title: string;
  stage_type: string;
  stage_label: string;
  status: string;
  resume: ApplicationResumeRead | null;
  schedule: Record<string, string> | null;
  evaluation: EvaluationRecord | null;
  pending_reschedule_request: RescheduleRequest | null;
  /** The ranges this evaluator is free in for this round, and the round's
   *  length HR cuts them into. */
  availability: { date: string; start: string; end: string }[];
  duration_minutes: number;
  /** HR has sent times to the applicant, who hasn't picked yet. */
  times_sent: boolean;
  /** The applicant has confirmed the interview time; until then the form
   *  is shown disabled and the server refuses a scorecard. */
  schedule_confirmed: boolean;
}
