/** The journey's shared measures and wording: the rail's geometry, dates,
 *  time since a stage began, and a stage's appointment. */

import type { StageInstance } from "../../../../../shared/api/applicant";

export interface ScheduleInfo {
  date: string;
  time: string;
  location?: string;
  mode?: "in_person" | "online";
  meeting_link?: string | null;
}

export const font = "var(--arkive-font)";

/** The width of the stage-node gutter: a 26px marker plus StageRow's 14px
 *  gap. Anything in the compact journey that is *about* the current stage
 *  — the "Up next" line, the completed-steps disclosure — has to start at
 *  the same left edge as that stage's own text, or the card ends up with
 *  two competing left margins and the action button reads as indented for
 *  no reason. Derived here rather than typed as 40 in three places. */
const NODE = 26;

const NODE_GAP = 14;

export const GUTTER = NODE + NODE_GAP;

/** "12 Aug" — short enough to sit at the end of a row without crowding
 * the label, which is the thing being read. */
export function shortDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/** "3 days" — the answer to the question every waiting applicant has.
 * Deliberately coarse: an applicant does not need "2 days, 4 hours". */
export function elapsedSince(iso: string): string | null {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  const days = Math.floor((Date.now() - then) / 86_400_000);
  if (days < 1) return "today";
  if (days === 1) return "1 day";
  return `${days} days`;
}

/**
 * When the current stage began — taken as the moment the stage before it
 * completed, since a StageInstance records only its own completion. The
 * first stage has nothing before it, so it reports nothing rather than
 * guessing at the application's creation time, which is not on this
 * payload.
 */
export function startedAt(stages: StageInstance[], index: number): string | null {
  for (let i = index - 1; i >= 0; i--) {
    if (stages[i].completed_at) return stages[i].completed_at;
  }
  return null;
}

export function scheduleOf(stage: StageInstance): ScheduleInfo | null {
  const schedule = stage.payload?.schedule as ScheduleInfo | undefined;
  return schedule?.date ? schedule : null;
}
