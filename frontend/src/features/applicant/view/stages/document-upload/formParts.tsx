/** The review form's building blocks: a labelled field, a removable
 *  entry card, and the empty-list line. */

import { inputStyle, label } from "./formStyle";

export function Field({ label: fieldLabel, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label style={label}>{fieldLabel}</label>
      <input type="text" value={value} onChange={(e) => onChange(e.target.value)} style={inputStyle} />
    </div>
  );
}

export function EntryCard({ children, onRemove }: { children: React.ReactNode; onRemove: () => void }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 12,
        border: "1px solid var(--surface-border)",
        borderRadius: "var(--radius)",
        padding: 14,
        marginTop: 10,
        position: "relative",
      }}
    >
      {children}
      <button
        type="button"
        onClick={onRemove}
        style={{
          gridColumn: "1 / -1",
          justifySelf: "end",
          fontFamily: "var(--arkive-font)",
          fontSize: "var(--text-xs)",
          fontWeight: 600,
          color: "var(--ink-400)",
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: 0,
        }}
      >
        Remove
      </button>
    </div>
  );
}

export function EmptyRow() {
  return (
    <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-400)", fontStyle: "italic", marginTop: 8 }}>
      Nothing here yet.
    </p>
  );
}
