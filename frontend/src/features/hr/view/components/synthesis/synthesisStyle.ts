/** Shared look for the synthesis sections: prose, aspect colours and the
 *  recommendation wording. */

import type { AgentCoverage } from "../../../../../shared/api/pipeline";
import { RECOMMENDATION_OPTIONS } from "../../../../../shared/lib/scorecard";
import type { TagTone } from "../../../../../shared/ui/Tag";

export const AGENT_BADGE: Record<AgentCoverage["status"], { label: string; tone: TagTone }> = {
  ran: { label: "Ran", tone: "green" },
  pending: { label: "Not yet run", tone: "neutral" },
  not_applicable: { label: "Not in this workflow", tone: "neutral" },
  derived: { label: "Computed live", tone: "neutral" },
};

export const RECOMMENDATION_LABELS = Object.fromEntries(
  RECOMMENDATION_OPTIONS.map((o) => [o.value, o.label]),
) as Record<string, string>;

/** On the form's 1-5 item scale. Green for a strong showing, accent only
 * where a category genuinely needs HR's attention — never as decoration. */
export function aspectColor(mean: number): string {
  if (mean >= 4) return "var(--success-text)";
  if (mean >= 3) return "var(--ink-600)";
  return "var(--accent)";
}

export const prose: React.CSSProperties = {
  margin: 0,
  fontSize: "var(--text-sm)",
  lineHeight: "var(--leading-normal)",
  color: "var(--ink-900)",
};
