/**
 * The rules HR's exam-session screens share: when a session counts as
 * started, what's wrong with a set of time windows, the one-click time
 * presets, turning a date range into days, spotting a session the job
 * already has, and the sentence for what a batch added. Pure, so it's
 * tested on its own; the server checks the same things regardless.
 */

import type { ExamSessionBatchResult, ExamSlot } from "../../../shared/api/pipeline";
import { timeNowInPhilippines, todayInPhilippines } from "../../../shared/lib/scheduleTime";

export interface WindowDraft {
  start: string;
  end: string;
}

/** One-click time windows for "Add sessions". */
export const WINDOW_PRESETS: { label: string; start: string; end: string }[] = [
  { label: "Morning", start: "09:00", end: "11:30" },
  { label: "Afternoon", start: "13:00", end: "16:30" },
];

/** The most days one "Add sessions" may cover; the server refuses more. */
export const MAX_DATES = 31;

/** Is this session over, or under way? Past sessions leave the lists. */
export function hasStarted(slot: Pick<ExamSlot, "date" | "time">, now: Date = new Date()): boolean {
  const today = todayInPhilippines(now);
  return slot.date < today || (slot.date === today && slot.time <= timeNowInPhilippines(now));
}

/** What's wrong with these windows, if anything, in the words the server
 *  would use. */
export function windowProblem(windows: WindowDraft[]): string | null {
  if (windows.length === 0) return "Add at least one time window.";
  if (windows.some((w) => !w.start || !w.end)) return "Enter a start and end time for each time window.";
  if (windows.some((w) => w.end <= w.start)) return "Each time window has to end after it starts.";
  const sorted = [...windows].sort((a, b) => a.start.localeCompare(b.start));
  for (let i = 1; i < sorted.length; i += 1) {
    if (sorted[i].start < sorted[i - 1].end) return "Time windows can't overlap.";
  }
  return null;
}

/** Every day from `from` to `to` (inclusive, YYYY-MM-DD), optionally
 *  leaving out Saturdays and Sundays. Calendar arithmetic in UTC, so no
 *  time zone can shift a day. Empty when the range is backwards. */
export function datesBetween(from: string, to: string, weekdaysOnly: boolean): string[] {
  if (!from || !to || to < from) return [];
  const days: string[] = [];
  const [fy, fm, fd] = from.split("-").map(Number);
  const cursor = new Date(Date.UTC(fy, fm - 1, fd));
  // a guard against a typo'd year turning into thousands of days
  for (let i = 0; i < 366; i += 1) {
    const iso = cursor.toISOString().slice(0, 10);
    if (iso > to) break;
    const weekday = cursor.getUTCDay();
    if (!weekdaysOnly || (weekday !== 0 && weekday !== 6)) days.push(iso);
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return days;
}

/** What makes two sessions "the same" for skipping repeats: exam, date,
 *  time window and place, case aside (as the server decides it). */
export function sessionKey(stage: string, date: string, start: string, end: string | null, location: string): string {
  return [stage, date, start, end ?? "", location.trim().toLowerCase()].join("|");
}

/** The sessions a draft would create, each marked when the job already
 *  has it (and so would be skipped). */
export function previewSessions(
  stage: string,
  dates: string[],
  windows: WindowDraft[],
  location: string,
  existing: ExamSlot[]
): { date: string; start: string; end: string; exists: boolean }[] {
  const have = new Set(existing.map((s) => sessionKey(s.stage_type, s.date, s.time, s.end_time, s.location)));
  const sortedWindows = [...windows].sort((a, b) => a.start.localeCompare(b.start));
  return [...dates].sort().flatMap((date) =>
    sortedWindows.map((w) => ({
      date,
      start: w.start,
      end: w.end,
      exists: have.has(sessionKey(stage, date, w.start, w.end, location)),
    }))
  );
}

/** Sentence for what "Add sessions" did, for the panel and the profile. */
export function addedSummary(result: ExamSessionBatchResult): string {
  const made = result.created.length;
  const base = `Added ${made} ${made === 1 ? "session" : "sessions"}.`;
  return result.skipped > 0
    ? `${base} ${result.skipped} ${result.skipped === 1 ? "was" : "were"} already there and skipped.`
    : base;
}
