import { isInterviewStage } from "../../../shared/lib/stageLabels";
import type { WorkflowStageDraft } from "./workflowStages";

/** The lengths an interview round can be, in minutes — the server's
 *  ALLOWED_DURATIONS (app/domain/interview_slots.py). An interview round's
 *  length is saved with the job and cuts the evaluator's free time into
 *  fixed slots. No other stage has a
 *  length. */
export const INTERVIEW_MINUTES = [15, 30, 45, 60, 90] as const;

/** An interview round's length from its draft, else the default
 *  (45 minutes for the first two rounds, 30 after). */
export function interviewMinutes(stage: WorkflowStageDraft): number {
  const minutes = stage.minutes;
  if (minutes !== undefined && (INTERVIEW_MINUTES as readonly number[]).includes(minutes)) return minutes;
  return stage.stageType.startsWith("interview_round_") && !["interview_round_1", "interview_round_2"].includes(stage.stageType)
    ? 30
    : 45;
}

/** What the job saves: minutes per interview round in the workflow. */
export function interviewDurations(stages: WorkflowStageDraft[]): Record<string, number> {
  return Object.fromEntries(
    stages.filter((s) => isInterviewStage(s.stageType)).map((s) => [s.stageType, interviewMinutes(s)])
  );
}

/** Puts a job's saved lengths back onto its stage drafts. */
export function withInterviewDurations(
  stages: WorkflowStageDraft[],
  durations: Record<string, number> | null | undefined
): WorkflowStageDraft[] {
  return stages.map((s) =>
    isInterviewStage(s.stageType) && durations?.[s.stageType] ? { ...s, minutes: durations[s.stageType] } : s
  );
}
