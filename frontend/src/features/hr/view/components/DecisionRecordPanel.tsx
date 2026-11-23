/**
 * The recorded hire or reject decision, shared by the HR Candidate
 * Profile and the Pre-201 package.
 */

import type { DecisionRecord } from "../../../../shared/api/pipeline";
import { shownText } from "../../../../shared/lib/displayText";
import { Tag } from "../../../../shared/ui/Tag";
import { applicationStatusTone } from "../../../../shared/lib/statusTags";
import { Card } from "../../../../shared/ui/Card";
import { SectionLabel } from "../../../../shared/ui/SectionLabel";

const STATUS_COPY: Record<string, string> = {
  hired: "Accepted",
  rejected: "Rejected",
  active: "Reopened",
  flagged: "Flagged",
};

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

/** Who closed the application, when, from which stage, why, and whether
 * they knowingly closed an incomplete record. Shared with the Pre-201
 * package so the permanent record states what HR saw at the moment of the
 * decision. No final synthesis score, as everywhere else: the HR
 * Director's office could not confirm how it is computed. */
export function DecisionRecordPanel({ decision }: { decision: DecisionRecord }) {
  const outcome = STATUS_COPY[decision.status] ?? decision.status;

  return (
    <Card padding={16}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <SectionLabel>Decision Record</SectionLabel>
        {/* Amber when a hire was closed over outstanding items: it needs
            attention, and it is the single most important fact on this
            panel. Otherwise the outcome in its status colour. */}
        <Tag tone={decision.acknowledged_incomplete ? "amber" : applicationStatusTone(decision.status)} dot>
          {decision.acknowledged_incomplete ? "Approved on an incomplete record" : outcome}
        </Tag>
      </div>

      <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-900)", margin: "10px 0 0", lineHeight: 1.6 }}>
        <strong style={{ fontWeight: 600 }}>{outcome}</strong>
        {decision.decided_by_name ? ` by ${decision.decided_by_name}` : ""} on{" "}
        {formatTimestamp(decision.decided_at)}
        {decision.decided_at_stage_label ? `, from ${shownText(decision.decided_at_stage_label)}.` : "."}
      </p>

      {decision.reason && (
        <p
          style={{
            fontFamily: "var(--arkive-font)",
            fontSize: "var(--text-base)",
            color: "var(--ink-600)",
            margin: "10px 0 0",
            paddingLeft: 12,
            borderLeft: "3px solid var(--surface-border)",
            lineHeight: 1.6,
          }}
        >
          {decision.reason}
        </p>
      )}

      {decision.blockers.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xs)", fontWeight: 700, color: "var(--ink-600)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Outstanding at the time of the decision
          </div>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
            {decision.blockers.map((blocker) => (
              <li
                key={`${blocker.key}-${blocker.label}`}
                style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", lineHeight: 1.5, marginBottom: 3 }}
              >
                <strong style={{ fontWeight: 600, color: "var(--ink-900)" }}>{shownText(blocker.label)}</strong>: {shownText(blocker.detail)}
              </li>
            ))}
          </ul>
        </div>
      )}

    </Card>
  );
}
