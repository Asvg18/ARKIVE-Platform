/** The titled card each settings section sits in. */

import type { ReactNode } from "react";

export function Panel({
  id,
  title,
  sub,
  children,
}: {
  id: string;
  title: string;
  sub?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="ark-panel" aria-labelledby={id}>
      <div className="ark-panel__head">
        <div>
          <h2 id={id} className="ark-panel__title">
            {title}
          </h2>
          {sub && <p className="ark-panel__sub ark-settings__sub">{sub}</p>}
        </div>
      </div>
      <div className="ark-panel__body ark-settings__body">{children}</div>
    </section>
  );
}
