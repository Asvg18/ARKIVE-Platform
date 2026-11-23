/**
 * The confirmation in front of hiring or rejecting a candidate.
 */

import { useEffect, useState, type CSSProperties } from "react";
import type { DecisionBlocker } from "../../../../shared/api/pipeline";
import { ConfirmDialog } from "../../../../shared/ui/ConfirmDialog";

const BLOCKER_GROUP_LABELS: Record<DecisionBlocker["key"], string> = {
  stage: "Pipeline position",
  shortlisting_outcome: "Shortlisting",
  interview_round: "Interview rounds",
  check_outcome: "Verification checks",
  criterion: "Decision Support scores",
};

/** Read order: where they are, whether they've been shortlisted, what's
 * outstanding round by round, which checks have no outcome, then what's
 * unscored -- roughly the order these actually happen in the pipeline. */
const BLOCKER_ORDER: DecisionBlocker["key"][] = [
  "stage",
  "shortlisting_outcome",
  "interview_round",
  "check_outcome",
  "criterion",
];

const FIELD_LABEL: CSSProperties = {
  fontFamily: "var(--arkive-font)",
  fontSize: "var(--text-xs)",
  fontWeight: 700,
  color: "var(--ink-600)",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};

/** Never a single unguarded click: the decision records who made it and
 * why, and an incomplete record must be acknowledged. The completeness
 * checklist is not computed here: the dialog opens plain, confirming sends
 * the real request, and a 409 brings back the server's own list, shown
 * with an acknowledgement HR must tick. The rules live in one place; a
 * client copy would be free to drift from the API's. */
export function DecisionDialog({
  open,
  mode,
  applicantName,
  blockers,
  message,
  submitting,
  error,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  mode: "hire" | "reject";
  applicantName: string;
  /** From the server's 409 — empty until the record is known incomplete. */
  blockers: DecisionBlocker[];
  /** The server's own summary sentence, shown once it has spoken. */
  message: string | null;
  submitting: boolean;
  error: string | null;
  onConfirm: (reason: string, acknowledged: boolean) => void;
  onCancel: () => void;
}) {
  const [reason, setReason] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);

  // Reset per opening, so a reason typed for one candidate can never
  // carry over into the next decision.
  useEffect(() => {
    if (open) {
      setReason("");
      setAcknowledged(false);
    }
  }, [open]);

  const isHire = mode === "hire";
  const needsAcknowledgement = isHire && blockers.length > 0;
  // Overriding the gate without saying why would leave an unexplained
  // hire, just with a name attached. Optional everywhere else, where a forced
  // reason only produces "n/a" typed a thousand times.
  const reasonRequired = needsAcknowledgement;
  const reasonMissing = reasonRequired && reason.trim() === "";

  const grouped = BLOCKER_ORDER.map((key) => ({
    key,
    label: BLOCKER_GROUP_LABELS[key],
    items: blockers.filter((blocker) => blocker.key === key),
  })).filter((group) => group.items.length > 0);

  return (
    <ConfirmDialog
      open={open}
      width={blockers.length > 0 ? 520 : 440}
      title={isHire ? "Approve this hire?" : `Reject ${applicantName}?`}
      description={
        message ??
        (isHire
          ? `This closes ${applicantName}'s application as accepted and compiles their Pre-Employment Records.`
          : `This closes ${applicantName}'s application. It can be reopened later if the decision changes.`)
      }
      confirmLabel={isHire ? "Approve Hire" : "Reject & Archive"}
      confirming={submitting}
      confirmDisabled={(needsAcknowledgement && !acknowledged) || reasonMissing}
      onConfirm={() => onConfirm(reason, acknowledged)}
      onCancel={onCancel}
    >
      {grouped.length > 0 && (
        <div
          style={{
            marginTop: 16,
            border: "1px solid var(--surface-border)",
            borderRadius: "var(--radius)",
            background: "var(--surface-bg)",
            padding: 14,
          }}
        >
          {grouped.map((group) => (
            <div key={group.key} style={{ marginBottom: 12 }}>
              <div style={FIELD_LABEL}>{group.label}</div>
              <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                {group.items.map((blocker) => (
                  <li
                    key={`${blocker.key}-${blocker.label}`}
                    style={{
                      fontFamily: "var(--arkive-font)",
                      fontSize: "var(--text-sm)",
                      color: "var(--ink-900)",
                      lineHeight: 1.5,
                      marginBottom: 4,
                    }}
                  >
                    <strong style={{ fontWeight: 600 }}>{blocker.label}</strong>
                    <span style={{ color: "var(--ink-600)" }}>: {blocker.detail}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      <label style={{ display: "block", marginTop: 16 }}>
        <span style={FIELD_LABEL}>Reason {reasonRequired ? "(required)" : "(optional)"}</span>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          maxLength={2000}
          placeholder={
            isHire
              ? "e.g. Unanimous across all three rounds; strongest exam percentile."
              : "e.g. Withdrew: accepted another offer."
          }
          style={{
            width: "100%",
            marginTop: 6,
            padding: "8px 10px",
            fontFamily: "var(--arkive-font)",
            fontSize: "var(--text-base)",
            color: "var(--ink-900)",
            border: "1px solid var(--surface-border)",
            borderRadius: "var(--radius)",
            resize: "vertical",
            boxSizing: "border-box",
          }}
        />
      </label>

      {needsAcknowledgement && (
        <label
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 10,
            marginTop: 14,
            padding: 12,
            borderRadius: "var(--radius)",
            background: "var(--warning-bg)",
            cursor: "pointer",
          }}
        >
          <input
            type="checkbox"
            checked={acknowledged}
            onChange={(e) => setAcknowledged(e.target.checked)}
            style={{ marginTop: 2, flexShrink: 0 }}
          />
          <span
            style={{
              fontFamily: "var(--arkive-font)",
              fontSize: "var(--text-sm)",
              color: "var(--warning-text)",
              lineHeight: 1.5,
            }}
          >
            I'm approving this hire on an incomplete record. This will be recorded
            against my name, along with the items listed above.
          </span>
        </label>
      )}

      {error && (
        <p
          style={{
            fontFamily: "var(--arkive-font)",
            fontSize: "var(--text-sm)",
            color: "var(--accent)",
            marginTop: 12,
            marginBottom: 0,
          }}
        >
          {error}
        </p>
      )}
    </ConfirmDialog>
  );
}
