/** A job's or a department's badge: its initials in a circle of the
 *  department's colour, the same shape and palette as a person's avatar.
 *  Pass the colour from `colorFor` (ranked within a list, so neighbours
 *  never share one) or `identityColor` (a job on its own). Decorative:
 *  the name beside it is what a screen reader hears. */
export function IdentityMark({
  initials,
  color,
  size = "md",
}: {
  initials: string;
  color: string;
  /** 26, 34, 40 or 52 px. */
  size?: "sm" | "md" | "lg" | "xl";
}) {
  return (
    <span className={size === "md" ? "ark-tile" : `ark-tile ark-tile--${size}`} aria-hidden="true" style={{ background: color }}>
      {initials}
    </span>
  );
}
