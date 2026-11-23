import { Link, useLocation } from "react-router-dom";
import { helpTopicFor } from "../../model/manual";
import { HelpIcon } from "../../../../shared/ui/icons";

/** The ? beside the bell in every portal's top bar (29 Oct 2026). It opens
 *  the user manual at the topic for the page it was pressed on, so "how
 *  do I book an exam?" lands on booking an exam, not on a table of
 *  contents. On a page the manual has no topic for, it opens the start. */
export function HelpButton() {
  const { pathname } = useLocation();
  const topic = helpTopicFor(pathname);
  return (
    <Link
      to={{ pathname: "/help", hash: topic ?? "" }}
      className="ark-icon-btn"
      aria-label="Help for this page"
      title="Help"
      aria-current={pathname === "/help" ? "page" : undefined}
    >
      <HelpIcon width={19} height={19} />
    </Link>
  );
}
