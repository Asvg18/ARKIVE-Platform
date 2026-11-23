/** Interview rounds: schedules, slots, scorecards on the profile,
 *  reschedules, and the evaluator pool. */

import type { EvaluatorRecommendation, GeneralEvaluationTier } from "../../lib/scorecard";
import type { StageType } from "./applications";

export interface InterviewSchedule {
  date: string;
  time: string;
  /** The slot's end, when the applicant picked a slot HR sent. */
  end_time?: string | null;
  mode: "in_person" | "online";
  location: string | null;
  meeting_link: string | null;
}

export interface RescheduleRequestSummary {
  id: number;
  proposed_date: string;
  proposed_time: string;
  reason: string | null;
}

export interface InterviewRatingEntry {
  label: string;
  assigned_evaluator_id: number | null;
  assigned_evaluator_name: string | null;
  assigned_evaluator_avatar_url?: string | null;
  item_ratings: Record<string, number | null> | null;
  computed_score: number | null;
  tier: GeneralEvaluationTier | null;
  /** The evaluator's own call, distinct from the derived tier. Null for
   *  evaluations submitted before this field existed. */
  recommendation: EvaluatorRecommendation | null;
  remarks: string | null;
  ai_summary: string | null;
  rubric_coverage_score: number | null;
  submitted_by: number | null;
  submitted_at: string | null;
  schedule: InterviewSchedule | null;
  /** The applicant's answer to the booked time; null for a time set
   *  before confirmations existed. */
  schedule_confirmation?: { response: "confirmed" | "unavailable" | null; note: string | null } | null;
  /** Evaluator → HR → applicant scheduling: the round's length, the
   *  evaluator's free ranges, those ranges cut into slots (taken = booked
   *  with the same evaluator elsewhere), and what HR last sent. */
  duration_minutes: number;
  availability: AvailabilityRange[];
  slot_choices: InterviewSlotChoice[];
  slot_offer: InterviewSlotOffer | null;
  reschedule_request: RescheduleRequestSummary | null;
}

export interface AvailabilityRange {
  date: string;
  start: string;
  end: string;
}

export interface InterviewSlotChoice {
  date: string;
  time: string;
  end_time: string;
  taken: boolean;
}

/** What HR sent the applicant. `response` is "picked" once they chose,
 *  "none_work" when none suited, null while still open. */
export interface InterviewSlotOffer {
  slots: { date: string; time: string }[];
  duration_minutes: number;
  mode: "in_person" | "online";
  location: string | null;
  meeting_link: string | null;
  sent_at: string;
  response: "picked" | "none_work" | null;
  note: string | null;
  responded_at: string | null;
}

export interface InterviewSlotOfferRequest {
  stage_type: StageType;
  slots: { date: string; time: string }[];
  mode: "in_person" | "online";
  location: string | null;
  meeting_link: string | null;
}

export interface RescheduleResolveRequest {
  decision: "approve" | "deny";
  date?: string | null;
  time?: string | null;
}

export interface EvaluatorAccount {
  id: number;
  full_name: string;
  email: string;
  created_at: string;
}

export interface EvaluatorAccountCreated extends EvaluatorAccount {
  temp_password: string;
}

export interface EvaluatorAccountCreateRequest {
  full_name: string;
  email: string;
}

export interface RequisitionEvaluator {
  id: number;
  evaluator_id: number;
  full_name: string;
  email: string;
  avatar_url?: string | null;
  /** From their own Account Settings. */
  job_title?: string | null;
  department?: string | null;
  /** True once this evaluator has submitted a scorecard for any of this
   *  job's candidates. The Workflow Builder hides the remove control then. */
  has_conducted: boolean;
  /** False once their account is switched off: they stay in the pool,
   *  but can't be given a new interview. */
  is_active: boolean;
}

export interface InterviewAssignmentRequest {
  stage_type: StageType;
  evaluator_id: number | null;
}
