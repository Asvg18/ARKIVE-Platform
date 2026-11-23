import { nounFor } from "../lib/paging";
import { Button } from "./Button";

/** The footer under a paged table: how many rows the list holds, then
 *  "Page 2 of 3" beside Previous and Next. Hidden when the list is empty,
 *  since the table's own empty state already says so. Pair it with
 *  `paginate`, which works out the page and keeps it in range. */
export function TablePager({
  total,
  page,
  pageCount,
  noun,
  onPage,
}: {
  /** Rows in the whole (searched) list, not just this page. */
  total: number;
  /** Zero-based, as `paginate` returns it. */
  page: number;
  pageCount: number;
  /** What a row is, singular: "job". */
  noun: string;
  onPage: (page: number) => void;
}) {
  if (total === 0) return null;
  return (
    <nav className="ark-pager" aria-label={`Pages of ${noun}s`}>
      <span>
        <strong>{total}</strong> {nounFor(total, noun)}
      </span>
      <span className="ark-pager__nav">
        <span className="ark-pager__page" aria-live="polite">
          Page <strong>{page + 1}</strong> of <strong>{pageCount}</strong>
        </span>
        <Button variant="secondary" size="sm" disabled={page === 0} onClick={() => onPage(page - 1)}>
          Previous
        </Button>
        <Button variant="secondary" size="sm" disabled={page >= pageCount - 1} onClick={() => onPage(page + 1)}>
          Next
        </Button>
      </span>
    </nav>
  );
}
