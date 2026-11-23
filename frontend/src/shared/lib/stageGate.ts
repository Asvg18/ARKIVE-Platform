/**
 * Reading the sufficiency gate's refusal: a 409 with code
 * "stage_incomplete" is a question, not an error, and opens
 * StageAdvanceDialog to record the stage as skipped.
 */

import { ApiError } from "../api/client";
import type { DecisionBlocker } from "../api/pipeline";

export interface StageGateRefusal {
  /** The server's own sentence, in this job's stage names. */
  message: string | null;
  blockers: DecisionBlocker[];
}

/**
 * The refusal if this error is the sufficiency gate, else null.
 *
 * Keyed on `code`, never on the status alone — a 409 is not specific
 * enough to open a dialog that offers to override something. One reading
 * for both screens that ask for the transition (the pipeline and the
 * candidate profile), since a wrong match either dead-ends where an
 * override was offered or offers one for a rule that has none.
 */
export function stageGateRefusal(err: unknown): StageGateRefusal | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null;
  const detail = err.detail as
    | { code?: string; message?: string; blockers?: DecisionBlocker[] }
    | null;
  if (!detail || detail.code !== "stage_incomplete") return null;
  return { message: detail.message ?? null, blockers: detail.blockers ?? [] };
}
