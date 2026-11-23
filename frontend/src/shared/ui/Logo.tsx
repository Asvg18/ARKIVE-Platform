/** The ARKIVE mark, the one place every shell and auth screen draws it
 * from. Served from public/brand/ rather than through the bundler, so the
 * favicon and any email or PDF template share its stable, unhashed URL. */
export function Logo({
  size = 36,
  withWordmark = false,
  subtitle,
}: {
  size?: number;
  /** Renders the ARKIVE wordmark beside the mark. The sidebars set their
   * own type for this, so it stays opt-in rather than the default. */
  withWordmark?: boolean;
  /** The small caps line under the wordmark — "UNIVERSITY HR",
   * "APPLICANT PORTAL", "EVALUATOR". Only meaningful with the wordmark. */
  subtitle?: string;
}) {
  const mark = (
    <img
      src="/brand/arkive-logo.png"
      alt=""
      aria-hidden="true"
      width={size}
      height={size}
      style={{ width: size, height: size, objectFit: "contain", flexShrink: 0, display: "block" }}
    />
  );

  if (!withWordmark) return mark;

  return (
    <span style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
      {mark}
      <span style={{ minWidth: 0 }}>
        <span
          style={{
            display: "block",
            fontSize: "var(--text-lg)",
            fontWeight: 800,
            // set wide, not tight -- this is the one place in the app
            // that's a *logotype* rather than an interface label, and
            // letterspaced capitals make a short word read as a mark
            // instead of a heading
            letterSpacing: "0.16em",
            // a variable with a fallback, so a dark shell can turn the
            // wordmark white without a second copy of this component
            color: "var(--logo-ink, var(--ink-950))",
            lineHeight: 1.1,
          }}
        >
          ARKIVE
        </span>
        {subtitle && (
          <span
            className="ark-truncate"
            style={{
              display: "block",
              fontSize: "var(--text-2xs)",
              fontWeight: 700,
              letterSpacing: "var(--track-wide)",
              textTransform: "uppercase",
              color: "var(--logo-sub, var(--ink-400))",
              marginTop: 1,
            }}
          >
            {subtitle}
          </span>
        )}
      </span>
    </span>
  );
}
