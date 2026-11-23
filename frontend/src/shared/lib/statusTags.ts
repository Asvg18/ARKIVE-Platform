/**
 * The colour each status takes as a tag, the same on every screen, so a
 * status never reads as a warning in one place and a final outcome in
 * another.
 *
 * Red is never "the item you selected" here: that is the accent's job.
 * Red is an outcome that has closed, against the candidate.
 */

import type { TagTone } from "../ui/Tag";

/** An application's status. Still in play is blue, a closer look amber,
 *  accepted green, rejected red, and a withdrawal (the applicant's own
 *  choice, not a verdict) neutral. */
export const APPLICATION_STATUS_TONE: Record<string, TagTone> = {
  active: "blue",
  flagged: "amber",
  hired: "green",
  rejected: "red",
  withdrawn: "neutral",
};

/** A job opening's status: open green, a draft amber (not live yet),
 *  closed neutral. */
export const JOB_STATUS_TONE: Record<string, TagTone> = {
  open: "green",
  draft: "amber",
  closed: "neutral",
};

/** The form's General Evaluation band: highly qualified green, qualified
 *  blue, not qualified amber, the same on every screen that shows it. */
export const TIER_TONE: Record<string, TagTone> = {
  highly_qualified: "green",
  qualified: "blue",
  not_qualified: "amber",
};

/** The evaluator's own recommendation, in the band's colours. */
export const RECOMMENDATION_TONE: Record<string, TagTone> = {
  highly_recommended: "green",
  recommended: "blue",
  not_recommended: "amber",
};

export function tierTone(tier: string | null | undefined): TagTone {
  return (tier && TIER_TONE[tier]) || "neutral";
}

export function recommendationTone(recommendation: string | null | undefined): TagTone {
  return (recommendation && RECOMMENDATION_TONE[recommendation]) || "neutral";
}

export function applicationStatusTone(status: string): TagTone {
  return APPLICATION_STATUS_TONE[status] ?? "neutral";
}

export function jobStatusTone(status: string): TagTone {
  return JOB_STATUS_TONE[status] ?? "neutral";
}
