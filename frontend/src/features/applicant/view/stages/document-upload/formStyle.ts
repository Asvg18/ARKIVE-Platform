/** The upload screens' shared type and field styles. */


export const heading: React.CSSProperties = { fontFamily: "var(--arkive-font)", fontSize: "var(--text-xl)", fontWeight: 700, color: "var(--ink-900)", margin: 0 };

export const subtext: React.CSSProperties = { fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", marginTop: 6 };

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

export const textareaStyle: React.CSSProperties = { ...inputStyle, resize: "vertical", marginTop: 6 };
