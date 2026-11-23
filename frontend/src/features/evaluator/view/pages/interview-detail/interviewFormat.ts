/** The interview page's rating options, formatting and form helpers. */

import { useEffect, useState } from "react";
import { CheckIcon, StarIcon, XIcon } from "../../../../../shared/ui/icons";
import { RATING_SCALE_LEGEND, SCORECARD_ITEM_CODES } from "../../../../../shared/lib/scorecard";
import type { EvaluatorRecommendation } from "../../../../../shared/lib/scorecard";

// Ascending, left to right, as rating scales read; 5-4-3-2-1 would put the
// most favourable option where the eye lands first. This is purely the
// order they are offered in. There is no N/A: every item takes a 1–5
// rating.
export const RATING_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 1, label: "1" },
  { value: 2, label: "2" },
  { value: 3, label: "3" },
  { value: 4, label: "4" },
  { value: 5, label: "5" },
];

export const RATING_WORD = Object.fromEntries(RATING_SCALE_LEGEND) as Record<number, string>;

export const RECOMMENDATION_ICON: Record<EvaluatorRecommendation, typeof StarIcon> = {
  highly_recommended: StarIcon,
  recommended: CheckIcon,
  not_recommended: XIcon,
};

export type ItemRatingsState = Record<string, number | undefined>;

export interface ScheduleInfo {
  date?: string;
  time?: string;
  mode?: string;
  location?: string | null;
  meeting_link?: string | null;
}

export function emptyItemRatings(): ItemRatingsState {
  return Object.fromEntries(SCORECARD_ITEM_CODES.map((code) => [code, undefined]));
}

export function formatElapsed(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function scrollBehavior(): ScrollBehavior {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
}

/** "2026-09-10" → "Thu, 10 Sep 2026" in the reader's own locale. Read as
 * a local date, not UTC midnight, so it never slips back a day. */
export function formatDate(date: string | undefined): string | null {
  if (!date) return null;
  const [y, m, d] = date.split("-").map(Number);
  if (!y || !m || !d) return date;
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** "09:30" → "9:30 AM". */
export function formatTime(time: string | undefined): string | null {
  if (!time) return null;
  const [h, min] = time.split(":").map(Number);
  if (Number.isNaN(h) || Number.isNaN(min)) return time;
  return new Date(2000, 0, 1, h, min).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/** Real elapsed wall-clock time since this page was opened, not a fabricated
 * "live interview" clock — ARKIVE has no live video session to time (the
 * interview already happened; the evaluator is reviewing it after the
 * fact). Adopted from the Figma's "Time Elapsed" treatment but grounded in
 * something real, per the project's rule against fabricating data. Stops
 * once an evaluation exists. */
export function useElapsedSeconds(active: boolean): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) return;
    const start = Date.now();
    const interval = setInterval(() => setSeconds(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(interval);
  }, [active]);
  return seconds;
}
