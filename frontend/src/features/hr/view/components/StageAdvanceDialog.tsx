/**
 * The confirmation in front of advancing a candidate past a stage that
 * recorded nothing.
 */

import { useEffect, useState, type CSSProperties } from "react";
import type { DecisionBlocker } from "../../../../shared/api/pipeline";
import { ConfirmDialog } from "../../../../shared/ui/ConfirmDialog";

const FIELD_LABEL: CSSProperties = {
  fontFamily: "var(--arkive-font)",
  fontSize: "var(--text-xs)",
  fontWeight: 700,
  color: "var(--ink-600)",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};

/** Opens only after the server has refused the advance, carrying the
 * server's own list of what is outstanding. The rules are not re-derived
 * here: a client-side copy of "what makes a stage complete" would be free
 * to drift from the one the API enforces. Refuse, then confirm, rather
 * than a checklist up front, so advancing a complete stage (the normal
 * case) stays a single click. Same shape as DecisionDialog. */
export function StageAdvanceDialog({
  open,
  candidateName,
  targetStageLabel,
  blockers,
  message,
  submitting,
  error,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  candidateName: string;
  targetStageLabel: string;
  /** The server's 409 list. This dialog only ever opens with one. */
  blockers: DecisionBlocker[];
  /** The server's own sentence, in HR's stage names. */
  message: string | null;
  submitting: boolean;
  error: string | null;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}) {
  const [reason, setReason] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);

  // Reset per opening, so a reason typed for one candidate can never
  // carry over into the next advance.
  useEffect(() => {
    if (open) {
      setReason("");
      setAcknowledged(false);
    }
  }, [open]);

  const reasonMissing = reason.trim() === "";

  return (
    <ConfirmDialog
      open={open}
      width={520}
      title="Advance without a complete record?"
      description={
        message ??
        `${candidateName}'s current stage has not recorded everything it should.`
      }
      confirmLabel={`Record as skipped & advance`}
      confirming={submitting}
      confirmDisabled={!acknowledged || reasonMissing}
      onConfirm={() => onConfirm(reason)}
      onCancel={onCancel}
    >
      <div
        style={{
          marginTop: 16,
          border: "1px solid var(--surface-border)",
          borderRadius: "var(--radius)",
          background: "var(--surface-bg)",
          padding: 14,
        }}
      >
        <div style={FIELD_LABEL}>Outstanding</div>
        <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
          {blockers.map((blocker) => (
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
              <strong>{blocker.label}</strong>: {blocker.detail}
            </li>
          ))}
        </ul>
      </div>

      <label
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: 10,
          marginTop: 16,
          fontFamily: "var(--arkive-font)",
          fontSize: "var(--text-sm)",
          color: "var(--ink-900)",
          lineHeight: 1.5,
          cursor: "pointer",
        }}
      >
        <input
          type="checkbox"
          checked={acknowledged}
          onChange={(e) => setAcknowledged(e.target.checked)}
          style={{ marginTop: 2, flexShrink: 0 }}
        />
        {/* Says what the record will say afterwards, not merely that a
            box was ticked. The stage stops claiming it was completed. */}
        <span>
          I understand this stage will be recorded as <strong>skipped</strong> rather than
          completed, with my name and reason attached, and that it will show that way on
          the candidate's record and to the applicant.
        </span>
      </label>

      <div style={{ marginTop: 14 }}>
        <label style={FIELD_LABEL} htmlFor="stage-skip-reason">
          Reason (required)
        </label>
        <textarea
          id="stage-skip-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          placeholder={`Why is ${candidateName} moving to ${targetStageLabel} without this?`}
          style={{
            display: "block",
            width: "100%",
            marginTop: 6,
            padding: "8px 10px",
            borderRadius: "var(--radius)",
            border: "1px solid var(--surface-border)",
            background: "var(--surface)",
            fontFamily: "var(--arkive-font)",
            fontSize: "var(--text-sm)",
            color: "var(--ink-900)",
            resize: "vertical",
            boxSizing: "border-box",
          }}
        />
      </div>

      {error && (
        <div
          role="alert"
          style={{
            marginTop: 12,
            background: "var(--warning-bg)",
            color: "var(--warning-text)",
            borderRadius: "var(--radius)",
            padding: "8px 10px",
            fontFamily: "var(--arkive-font)",
            fontSize: "var(--text-sm)",
            fontWeight: 600,
          }}
        >
          {error}
        </div>
      )}
    </ConfirmDialog>
  );
}
