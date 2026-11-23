/** The two frames every synthesis section sits in. */

import type { ReactNode } from "react";

/** A titled section of the synthesis. */
export function Panel({
  id,
  title,
  aside,
  sub,
  children,
  bodyless = false,
}: {
  /** An anchor, for a link that lands on this section. */
  id?: string;
  title: string;
  aside?: ReactNode;
  sub?: ReactNode;
  children: ReactNode;
  /** For a body that lays out its own padding (a split, a table). */
  bodyless?: boolean;
}) {
  return (
    <section className="ark-panel" id={id}>
      <div className="ark-panel__head">
        <div style={{ minWidth: 0 }}>
          <h2 className="ark-panel__title">{title}</h2>
          {sub && <p className="ark-panel__sub">{sub}</p>}
        </div>
        {aside}
      </div>
      {bodyless ? children : <div className="ark-panel__body">{children}</div>}
    </section>
  );
}

/** A panel that stays shut until asked — the working, not the answer.
 * Native <details>, so it is keyboard-correct for free and the Pre-201
 * package can open every one with a prop. */
export function DisclosurePanel({
  title,
  detail,
  open,
  children,
}: {
  title: string;
  detail: string;
  open: boolean;
  children: ReactNode;
}) {
  return (
    <section className="ark-panel">
      <details open={open}>
        <summary>
          <span className="ark-panel__summary-title">
            <span className="ark-disclosure" aria-hidden="true" />
            {title}
          </span>
          <span className="ark-panel__summary-detail">{detail}</span>
        </summary>
        {children}
      </details>
    </section>
  );
}
