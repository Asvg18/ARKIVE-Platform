import type { CSSProperties, ReactNode } from "react";

export type TagTone = "neutral" | "blue" | "green" | "amber" | "red" | "violet" | "teal";

/** A soft colour pill: fully rounded, a light tint, and darker text of
 *  the same colour. The one tag style everywhere, so a tone means the
 *  same thing on every screen. Every
 *  tone's text passes 4.5:1 on its own tint.
 *
 *  `dot` marks a status. `dotColor` gives the dot a colour of its own,
 *  such as a department's, on a neutral tag. */
export function Tag({
  children,
  tone = "neutral",
  dot = false,
  dotColor,
  className,
  title,
}: {
  children: ReactNode;
  tone?: TagTone;
  dot?: boolean;
  dotColor?: string;
  className?: string;
  /** A tooltip, for a tag whose word needs a sentence behind it. */
  title?: string;
}) {
  return (
    <span className={["ark-tag", `ark-tag--${tone}`, className].filter(Boolean).join(" ")} title={title}>
      {(dot || dotColor) && (
        <span
          className="ark-tag__dot"
          aria-hidden="true"
          style={dotColor ? ({ "--tag-dot": dotColor } as CSSProperties) : undefined}
        />
      )}
      {children}
    </span>
  );
}
