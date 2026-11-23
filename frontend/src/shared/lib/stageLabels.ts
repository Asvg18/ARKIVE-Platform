// interview_hr_director/dept_head/vp are legacy, superseded by the
// generic interview_round_1..6 slots. kept only so already-in-flight
// applications on those stages still render a label. reference_check and
// background_check are retired outright (see RETIRED_STAGES below) but
// stay here because the backend enum still has them.
export const STAGE_LABELS: Record<string, string> = {
  document_upload: "Document Upload",
  skill_matching: "Pre-Screening",
  shortlisting: "Shortlisting",
  examination: "Examination",
  // the first exam is just "Examination"
  examination_1: "Examination",
  examination_2: "Examination 2",
  examination_3: "Examination 3",
  examination_4: "Examination 4",
  interview_hr_director: "HR Administrator Interview",
  interview_dept_head: "Department Head Interview",
  interview_vp: "VP Interview",
  interview_round_1: "Interview Round 1",
  interview_round_2: "Interview Round 2",
  interview_round_3: "Interview Round 3",
  interview_round_4: "Interview Round 4",
  interview_round_5: "Interview Round 5",
  interview_round_6: "Interview Round 6",
  reference_check: "Reference Check",
  background_check: "Background Check",
  final_decision: "Final Decision",
  onboarding: "Onboarding",
};

/** Reference and background checks, retired. No workflow uses
 * them and the server refuses a workflow that does; they are labelled
 * above only because the backend enum still carries them. */
export const RETIRED_STAGES: ReadonlySet<string> = new Set(["reference_check", "background_check"]);

/** Static fallback only -- a job's actual per-round label (e.g. "Panel
 * Interview") is per-job data resolved server-side and arrives as a
 * sibling `*_label` field on the API response wherever one exists;
 * prefer that over this function when it's available. */
export function stageLabel(stage: string | null): string {
  if (!stage) return "–";
  return STAGE_LABELS[stage] ?? stage;
}

/** A stage in one job's own words: the name HR gave an interview round
 * or examination for this job, else the static label. Mirrors backend
 * stage_labels.resolve_stage_label(), including treating an empty
 * override as no override. */
export function jobStageLabel(
  stage: string | null,
  job: {
    interview_round_labels?: Record<string, string> | null;
    examination_labels?: Record<string, string> | null;
  } | null
): string {
  if (!stage) return "–";
  return job?.interview_round_labels?.[stage] || job?.examination_labels?.[stage] || stageLabel(stage);
}

/** True for both the legacy fixed slots and the generic
 * interview_round_1..6 slots, which share this prefix by construction.
 * Mirrors backend dfa.is_interview_stage(). */
export function isInterviewStage(stage: string | null): boolean {
  return !!stage && stage.startsWith("interview_");
}

/** True for the legacy singular `examination` slot and the generic
 * examination_1..4 slots. Mirrors backend dfa.is_exam_stage(). */
export function isExamStage(stage: string | null): boolean {
  return !!stage && stage.startsWith("examination");
}

export const STATUS_LABELS: Record<string, string> = {
  active: "Active",
  rejected: "Rejected",
  // Shown as "Accepted", the word HR uses. The enum value stays `hired`
  // (no migration, every status === "hired" check is unaffected); only
  // the displayed word differs.
  hired: "Accepted",
  flagged: "Flagged for Review",
  withdrawn: "Withdrawn",
};

/** The same statuses in the words an applicant is shown. Differs from
 * STATUS_LABELS in one place: a rejected application reads "Unlikely to
 * progress" — JobStreet's phrasing, and the gentler way to tell someone
 * their application has stopped. HR keeps "Rejected", which is the
 * decision they recorded and the word they work in. */
export const APPLICANT_STATUS_LABELS: Record<string, string> = {
  ...STATUS_LABELS,
  rejected: "Unlikely to progress",
};
