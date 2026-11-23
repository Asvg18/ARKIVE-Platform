/** The Decision Support synthesis shown on the Candidate Profile. */

import type { EvaluatorRecommendation, GeneralEvaluationTier } from "../../lib/scorecard";

/**
 * The consolidated Decision Support read. `final_synthesis_score` is
 * deliberately all-or-nothing -- the WSM assumes all four criteria are
 * present, so a missing input is never treated as zero. These types
 * carry the *explanation* alongside that null, so the UI can show it.
 */
export type CriterionKey =
  | "skill_match"
  | "exam_percentile"
  | "executive_consensus"
  | "interview_rubric";

/**
 * "missing" = this job has the stage, the data just isn't recorded yet.
 * "not_applicable" = this job's workflow has no such stage, so the
 * criterion can never be recorded and the final score is permanently
 * unreachable. Very different facts, so they must not render alike.
 */
export type CriterionStatus = "available" | "missing" | "not_applicable";

export type AgentStatus = "ran" | "pending" | "not_applicable" | "derived";

export interface SynthesisCriterion {
  key: CriterionKey;
  label: string;
  /** Institutional weight from thesis 5.1.2.8 — C1 .569, C2 .037, C3 .043, C4 .351. */
  weight: number;
  status: CriterionStatus;
  /** Normalized 0-100, exactly as fed to the WSM. */
  value: number | null;
  /** The same number in its original scale, e.g. "3.90 / 5". */
  display_value: string | null;
  /** value * weight — points this criterion actually contributes. */
  contribution: number | null;
  detail: string;
}

export interface AgentRunRead {
  id: number;
  agent_name: string;
  label: string;
  triggered_by_stage: string;
  triggered_by_stage_label: string;
  created_at: string;
}

export interface AgentCoverage {
  agent_name: string;
  label: string;
  duty: string;
  /** "derived" agents are pure functions recomputed on read — no run event. */
  kind: "event" | "derived";
  status: AgentStatus;
  run_count: number;
  last_run_at: string | null;
}

/** One HRD-F-APIEF category, averaged across every evaluated round. */
export interface AspectRead {
  code: string;
  label: string;
  /** The form's own 1-5 item scale, deliberately not rescaled to 0-100. */
  mean: number;
  band: string;
  rounds_counted: number;
  items_rated: number;
}

export interface SynthesisRoundRead {
  stage_type: string;
  label: string;
  evaluator_name: string | null;
  evaluator_avatar_url?: string | null;
  score: number | null;
  tier: GeneralEvaluationTier | null;
  tier_label: string | null;
  recommendation: EvaluatorRecommendation | null;
  /** Rated furthest from the rest of the chain, in either direction. */
  is_outlier: boolean;
}

export interface AgreementRead {
  submitted_rounds: number;
  total_rounds: number;
  unanimous: boolean;
  summary: string;
  rounds: SynthesisRoundRead[];
}

/** A requirement verdict still disputed after a re-check: the
 *  requirement in HR's own words, and the note on why, which carries the
 *  AI's reasoning. Kept apart so only the note is tidied for display. */
export interface DisputedRequirement {
  requirement: string;
  note: string;
}

export type RequirementVerdict = "met" | "partial" | "not_met";

export type MatchBasis = "direct" | "equivalent" | "related" | "transferable" | "none";

/** One requirement's part in the resume match score: its similarity to
 *  the resume (the arithmetic half) and the verified verdict on it (the
 *  coverage half). Similarity is null on older scores, which stored the
 *  verdicts only. */
export interface RequirementScore {
  requirement: string;
  semantic_score: number | null;
  keyword_score: number | null;
  similarity_score: number | null;
  closest_resume_text: string;
  verdict: RequirementVerdict;
  basis: MatchBasis;
  reasoning: string;
  evidence_quote: string;
  verified: boolean;
  note: string;
  points: number;
}

export interface MatchBreakdown {
  score_method: string;
  match_score: number;
  arithmetic_score: number | null;
  semantic_score: number | null;
  keyword_score: number | null;
  requirement_coverage: number | null;
  semantic_weight: number;
  coverage_weight: number;
  verdict_points: Record<string, number>;
  flag_threshold: number;
  requirements: RequirementScore[];
}

export interface EvidenceRead {
  match_score: number | null;
  match_reading: string;
  match_strengths: string[];
  match_gaps: string[];
  /** The Critic did not sign off this resume read: show it marked, not as findings. */
  match_unverified?: boolean;
  /** Requirement verdicts still disputed after a re-check. */
  match_disputed?: DisputedRequirement[];
  /** How match_score was arrived at — shown beside it as a rubric. */
  match_breakdown?: MatchBreakdown | null;
  exam_score: number | null;
  exam_rank: number | null;
  exam_cohort: number | null;
  exam_percentile: number | null;
}

export interface BriefRead {
  verdict: string;
  rationale: string;
  /** The facts the brief was written from — not necessarily today's. */
  facts: string[];
  /** True when the record has changed since the brief was written. */
  stale: boolean;
}

/** One fact behind the verdict and which way it points — `attention`
 *  is what HR should look at before deciding. `items` holds what a fact
 *  counts (the unaddressed requirements themselves). */
export interface HeadlineSignal {
  key: "evaluators" | "exam_rank" | "requirement_gaps";
  label: string;
  detail: string;
  tone: "positive" | "neutral" | "attention";
  items: string[];
}

export interface HeadlineRead {
  band: string | null;
  score: number | null;
  signals: HeadlineSignal[];
}

/** One fact-sheet line broken out for layout. `text` is the sentence
 *  itself (what the Decision Brief Agent read); the rest is that fact as
 *  data. */
export interface FactRead {
  key:
    | "position"
    | "skill_match"
    | "requirement_gaps"
    | "rubric"
    | "strongest_area"
    | "weakest_area"
    | "rubric_even"
    | "agreement"
    | "exam";
  label: string;
  value: string | null;
  note: string | null;
  items: string[];
  scores: { name: string; value: number }[];
  text: string;
}

export interface CandidateSynthesis {
  final_synthesis_score: number | null;
  overall_tier: GeneralEvaluationTier | null;
  criteria: SynthesisCriterion[];
  criteria_available: number;
  /** Below 4 means this workflow can never produce a final score. */
  criteria_applicable: number;
  criteria_total: number;
  blocked_reason: string | null;
  headline: HeadlineRead;
  brief: BriefRead | null;
  fact_sheet: string[];
  /** The current fact sheet, one row per line, for layout. */
  fact_rows: FactRead[];
  fact_fingerprint: string;
  aspects: AspectRead[];
  agreement: AgreementRead;
  evidence: EvidenceRead;
  agents: AgentCoverage[];
  agent_trail: AgentRunRead[];
}
