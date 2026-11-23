/** User Management's shared heading, label and input styles. */


export const sectionHeading: React.CSSProperties = {
  fontFamily: "var(--arkive-font)",
  fontSize: "var(--text-lg)",
  fontWeight: 650,
  color: "var(--ink-900)",
  marginTop: 0,
  marginBottom: 0,
};

export const label: React.CSSProperties = {
  display: "block",
  fontFamily: "var(--arkive-font)",
  fontSize: "var(--text-xs)",
  fontWeight: 700,
  color: "var(--ink-600)",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
  marginBottom: 4,
};

export const inputStyle: React.CSSProperties = {
  display: "block",
  width: "100%",
  padding: "10px 12px",
  borderRadius: "var(--radius)",
  border: "1px solid var(--surface-border)",
  background: "var(--surface)",
  fontFamily: "var(--arkive-font)",
  fontSize: "var(--text-base)",
  color: "var(--ink-900)",
  boxSizing: "border-box",
};
