import type { ReactNode } from "react";
import { AlertIcon, CheckIcon } from "./icons";

/** A message inside a form or panel: an icon, a one-line title, optional
 *  detail beneath, and optionally the one action that helps. Styled by
 *  .ark-alert in components.css.
 *
 *  `success` is for confirming something just happened in place (a
 *  replacement saved), where a toast would vanish before it was read. */
export function Alert({
  tone,
  title,
  children,
  action,
}: {
  tone: "warning" | "danger" | "success";
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
}) {
  const Icon = tone === "success" ? CheckIcon : AlertIcon;
  return (
    <div role={tone === "success" ? "status" : "alert"} className={`ark-alert ark-alert--${tone}`}>
      <Icon width={16} height={16} className="ark-alert__icon" aria-hidden="true" />
      <div className="ark-alert__text">
        <p className="ark-alert__title">{title}</p>
        {children}
        {action && <div className="ark-alert__action">{action}</div>}
      </div>
    </div>
  );
}
