import type { ReactNode } from "react";
import { InfoTip } from "./InfoTip";

/** What a page is for, and what is worth knowing before using it. */
export type PageInfo = {
  /** One or two sentences: the page's purpose. */
  summary: ReactNode;
  /** Short rules of the road — each one a fact, not a restatement. */
  points?: ReactNode[];
};

/** The title block at the top of every signed-in page.
 *
 * Each page used to write its own: the same <h1> restyled inline sixteen
 * times, with the description at 15px on some pages and 17px on others,
 * a bottom gap anywhere from 0 to 32px, and a different width on each.
 * Moving between pages, the title jumped and the content started at a
 * different height every time — the clearest sign that nobody had set
 * the layout, each screen had just been left where it fell.
 *
 * One component, so the rhythm is decided once: title, the page's main
 * action pinned top-right, and the same gap to the content beneath on
 * every screen.
 *
 * `info` is the explanation of the page — what it is for and the rules
 * worth knowing. It lives behind an ⓘ beside the title rather than as a
 * paragraph under it: read once, it is furniture every visit after, and
 * three lines of it pushed every HR page's actual work down the screen.
 * `description` stays for a short line of live context ("12 candidates
 * across 5 openings", "Accepted 3 Sep") — data, not instructions.
 *
 * `above` is for a back link or breadcrumb that belongs over the title
 * rather than in the description. */
export function PageHeader({
  title,
  description,
  info,
  actions,
  above,
}: {
  title: ReactNode;
  description?: ReactNode;
  info?: PageInfo;
  actions?: ReactNode;
  above?: ReactNode;
}) {
  return (
    <header className="ark-page-head">
      {above && <div className="ark-page-head__above">{above}</div>}
      <div className="ark-page-head__row">
        <div className="ark-page-head__text">
          <div className="ark-page-head__title-row">
            <h1 className="ark-page-head__title">{title}</h1>
            {info && (
              <InfoTip ariaLabel="About this page" width={340} className="ark-tip--about">
                <div className="ark-about">
                  <p className="ark-about__eyebrow">About this page</p>
                  <p className="ark-about__summary">{info.summary}</p>
                  {info.points && info.points.length > 0 && (
                    <ul className="ark-about__points">
                      {info.points.map((point, i) => (
                        <li key={i}>{point}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </InfoTip>
            )}
          </div>
          {description && <p className="ark-page-head__desc">{description}</p>}
        </div>
        {actions && <div className="ark-page-head__actions">{actions}</div>}
      </div>
    </header>
  );
}
