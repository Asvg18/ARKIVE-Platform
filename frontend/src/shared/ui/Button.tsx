import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "outline" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

/** The app's button.
 *
 * A class, not an inline style object -- React's `style` prop can't
 * express :hover, :focus-visible or :active, so every button was inert
 * under the cursor. A control that doesn't answer the pointer is the
 * loudest tell of an unfinished interface.
 *
 * Geometry (height, radius, transition) is shared by every variant so a
 * mixed row lines up without anyone nudging a margin; `style` still
 * passes through for one-off cases relying on it. */
export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...rest
}: {
  variant?: Variant;
  size?: Size;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      className={[
        "ark-btn",
        `ark-btn--${variant}`,
        size !== "md" ? `ark-btn--${size}` : "",
        className ?? "",
      ]
        .filter(Boolean)
        .join(" ")}
    />
  );
}
