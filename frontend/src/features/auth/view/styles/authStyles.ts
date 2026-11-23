/** The shared look of the signed-out screens: sign in, sign up, accept
 * an invite, forgot password, reset password.
 *
 * Extracted once there were five of them. Each page had grown its own
 * identical copy of these three objects, which is fine for two and a
 * slow drift for five -- the point at which one screen's field quietly
 * stops matching the next one's. */
export const authLabel: React.CSSProperties = {
  display: "block",
  fontFamily: "var(--arkive-font)",
  fontSize: "var(--text-xs)",
  fontWeight: 700,
  color: "var(--ink-600)",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
  marginBottom: 6,
};

export const authInputStyle: React.CSSProperties = {
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

export const authHint: React.CSSProperties = {
  fontFamily: "var(--arkive-font)",
  fontSize: "var(--text-xs)",
  color: "var(--ink-400)",
  margin: "6px 0 0",
};

/** A field that failed its check: the border and a soft ring in the
 * danger colour, laid over authInputStyle. The whole `border` shorthand,
 * not `borderColor`: React clears the longhands it does not name when a
 * shorthand and a longhand meet, which left the field with no border. */
export const authInputInvalid: React.CSSProperties = {
  border: "1px solid var(--danger-text)",
  boxShadow: "0 0 0 3px var(--danger-bg)",
};

/** The sentence under a field saying what is wrong with it. Replaces the
 * field's hint while it shows, so the two never stack. */
export const authFieldError: React.CSSProperties = {
  display: "flex",
  alignItems: "flex-start",
  gap: 6,
  fontFamily: "var(--arkive-font)",
  fontSize: "var(--text-xs)",
  fontWeight: 500,
  lineHeight: 1.45,
  color: "var(--danger-text)",
  margin: "6px 0 0",
};
