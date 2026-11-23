/** Mirrors backend/app/schemas/skill_match.py. */
export interface RequisitionMatch {
  requisition_id: number;
  title: string;
  department: string;
  semantic_score: number;
  keyword_score: number;
  combined_score: number;
}

/** A suggested alternative opening, as the applicant is allowed to see it
 * — no score of any kind (not even a positive-framed one), just what the
 * job is. Contrast with RequisitionMatch, which HR sees in full. */
export interface ApplicantJobSuggestion {
  requisition_id: number;
  title: string;
  department: string;
}

/** What the applicant themselves is allowed to see on their own
 * skill_matching StageInstance payload. Score, semantic/keyword
 * breakdown, top_skills, strengths, gaps, and the critical summary are
 * HR-only -- showing a candidate a critical AI analysis of their own
 * shortcomings is discouraging regardless of outcome (see
 * backend/app/api/applicant/detail.py::_redact_skill_matching_payload). The
 * backend strips those fields out entirely, so this type only has the
 * two keys that actually arrive on the wire. */
export interface ApplicantSkillMatchPayload {
  answers: string[];
  suggested_requisitions: ApplicantJobSuggestion[];
}

export function getApplicantSkillMatchPayload(
  stageInstances: { stage_type: string; payload: Record<string, unknown> | null }[]
): ApplicantSkillMatchPayload | null {
  const instance = stageInstances.find((s) => s.stage_type === "skill_matching");
  return (instance?.payload as ApplicantSkillMatchPayload | undefined) ?? null;
}
