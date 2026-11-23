/** Find Jobs' sort and deadline choices, and how a posting's dates and
 *  text lines are worded. */

import type { JobListItem } from "../../../../../shared/api/public";

export type SortKey = "newest" | "closing" | "title";

export type DeadlineKey = "any" | "week" | "month" | "open";

export const SORTS: Record<SortKey, string> = {
  newest: "Newest first",
  closing: "Closing soonest",
  title: "Title (A–Z)",
};

export const DEADLINES: Record<DeadlineKey, string> = {
  any: "Any deadline",
  week: "Closing this week",
  month: "Closing this month",
  open: "Open until filled",
};

export function timeAgo(iso: string): string {
  const hours = Math.floor((Date.now() - new Date(iso).getTime()) / 3_600_000);
  if (hours < 1) return "Just posted";
  if (hours < 24) return `Posted ${hours}h ago`;
  return `Posted ${Math.floor(hours / 24)}d ago`;
}

function daysUntil(dateStr: string): number {
  return Math.ceil((new Date(dateStr).getTime() - Date.now()) / 86_400_000);
}

export function deadlineLabel(dateStr: string | null): string {
  if (!dateStr) return "Open until filled";
  const days = daysUntil(dateStr);
  if (days < 0) return "Applications closed";
  if (days === 0) return "Closes today";
  if (days === 1) return "Closes in 1 day";
  return `Closes in ${days} days`;
}

export function isSoon(dateStr: string | null): boolean {
  return dateStr != null && daysUntil(dateStr) <= 14;
}

export function matchesDeadline(job: JobListItem, key: DeadlineKey): boolean {
  if (key === "any") return true;
  if (key === "open") return job.application_deadline == null;
  if (!job.application_deadline) return false;
  const days = daysUntil(job.application_deadline);
  return days >= 0 && days <= (key === "week" ? 7 : 31);
}

export function lines(text: string | null): string[] {
  return (text ?? "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}
