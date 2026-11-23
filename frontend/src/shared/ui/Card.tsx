import type { CSSProperties, ReactNode } from "react";

/** A surface. `elevation` is how far the card sits off the page, not
 * how important it is -- a raised card with nothing urgent in it just
 * looks loud.
 *
 * `interactive` is separate and deliberate: it adds hover/active
 * motion, and belongs only on a card you actually click. A card that
 * merely *contains* clickable things must not move under the cursor, or
 * the whole page feels nervous. */
export function Card({
  children,
  padding = 24,
  elevation = "sm",
  interactive = false,
  className,
  style,
}: {
  children: ReactNode;
  padding?: string | number;
  elevation?: "none" | "xs" | "sm" | "md";
  interactive?: boolean;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div
      className={[
        "ark-card",
        elevation === "none" ? "ark-card--flat" : "",
        elevation === "md" ? "ark-card--raised" : "",
        interactive ? "ark-card--interactive" : "",
        className ?? "",
      ]
        .filter(Boolean)
        .join(" ")}
      style={{ padding, ...style }}
    >
      {children}
    </div>
  );
}
