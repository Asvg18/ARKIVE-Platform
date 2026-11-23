import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { RequisitionSummary } from "../../../../shared/api/pipeline";
import { Card } from "../../../../shared/ui/Card";
import { Button } from "../../../../shared/ui/Button";
import { IdentityMark } from "../../../../shared/ui/IdentityMark";
import { colorFor, departmentPalette, initials } from "../../../../shared/lib/identity";
import { ArrowRightIcon, LockIcon, PencilIcon, SearchIcon } from "../../../../shared/ui/icons";

type Filter = "all" | "editable" | "locked";
type SortKey = "title" | "department" | "active";
type Sort = { key: SortKey; dir: "asc" | "desc" };

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "editable", label: "Editable" },
  { key: "locked", label: "Locked" },
];

const collator = new Intl.Collator(undefined, { sensitivity: "base", numeric: true });

function isEditable(req: RequisitionSummary): boolean {
  return req.active_candidate_count === 0;
}

function compare(a: RequisitionSummary, b: RequisitionSummary, sort: Sort): number {
  const primary =
    sort.key === "active"
      ? a.active_candidate_count - b.active_candidate_count
      : collator.compare(a[sort.key], b[sort.key]);
  // Ties fall back to the title so equal rows never shuffle between renders.
  const ordered = primary !== 0 ? primary : collator.compare(a.title, b.title);
  return sort.dir === "asc" ? ordered : -ordered;
}

/** The "pick a job, then configure one thing about it" list shared by the
 * Workflow Builder and Pre-Screening Questions pickers.
 *
 * It replaced a three-up card grid. Cards scale by area: eighteen jobs were
 * six rows of boxes, each repeating its status as a chip, and finding one
 * meant scanning a page of equally loud tiles. A table scales by rows —
 * columns line up, so the eye reads down Status or Active instead of
 * hunting across cards — and search, a status filter and sortable headings
 * keep it manageable as the list grows.
 *
 * The status emphasis is also inverted from the cards. There the locked
 * majority each carried an amber chip, so the page was mostly warning
 * colour for a normal state. Here the rows HR can act on say "Edit" in the
 * accent and the locked ones recede to a grey lock, which is where
 * attention belongs.
 *
 * Status and action share one column. An "Editable" chip with an "Edit"
 * link beside it said the same thing twice, and a second column of links
 * down every row was the busiest thing on the page. Each row now carries
 * one icon-and-word — ✎ Edit or 🔒 Locked — so the icons line up down the
 * column and so do the words. Where the row opens, that label is a real
 * link, so keyboard, middle-click and screen readers all work; the rest of
 * the row is a mouse convenience on top of that, not the only way in. An
 * arrow fades in beside it on hover, which is how a locked workflow (that
 * still opens) says so without a "View" link on every row. */
export function JobPickerTable({
  requisitions,
  hrefFor,
  lockedOpens,
  subject,
  lockedHint,
}: {
  requisitions: RequisitionSummary[];
  hrefFor: (req: RequisitionSummary) => string;
  /** Whether a job with active candidates can still be opened read-only.
   *  True for the workflow (names, pool and slots stay editable), false
   *  for the questions, which genuinely cannot change. */
  lockedOpens: boolean;
  /** What a row opens, for the link's accessible name: "workflow". */
  subject: string;
  /** What "Locked" means on this page, shown on hover over a locked row. */
  lockedHint: string;
}) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>({ key: "title", dir: "asc" });

  /** Built from the full list, as everywhere else, so a department keeps
   *  its hue whatever the search or filter leaves on screen. */
  const deptColors = departmentPalette(requisitions.map((r) => r.department));

  const q = query.trim().toLowerCase();
  const matching = q
    ? requisitions.filter((r) => r.title.toLowerCase().includes(q) || r.department.toLowerCase().includes(q))
    : requisitions;

  // Counts follow the search, so "Editable 2" means two of what you are
  // looking at, not two somewhere in the full list.
  const counts: Record<Filter, number> = {
    all: matching.length,
    editable: matching.filter(isEditable).length,
    locked: matching.filter((r) => !isEditable(r)).length,
  };

  const rows = matching
    .filter((r) => filter === "all" || (filter === "editable") === isEditable(r))
    .sort((a, b) => compare(a, b, sort));

  function toggleSort(key: SortKey) {
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
        : // Busiest first is the useful default for a count; A–Z for text.
          { key, dir: key === "active" ? "desc" : "asc" }
    );
  }

  function sortHeader(
    key: SortKey,
    label: string,
    opts: { align?: "left" | "center"; width?: string | number; className?: string; title?: string } = {}
  ) {
    const active = sort.key === key;
    return (
      <th
        aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
        className={opts.className}
        style={{ textAlign: opts.align ?? "left", width: opts.width }}
        title={opts.title}
      >
        <button
          type="button"
          className={`ark-th-sort${opts.align === "center" ? " ark-th-sort--center" : ""}`}
          data-active={active}
          onClick={() => toggleSort(key)}
        >
          {label}
          <span className="ark-th-sort__mark" aria-hidden="true">
            {active && sort.dir === "desc" ? "↓" : "↑"}
          </span>
        </button>
      </th>
    );
  }

  return (
    <Card padding={0} elevation="md">
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          padding: "14px 24px",
        }}
      >
        <div className="ark-tabs" role="group" aria-label="Filter jobs by status">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              className="ark-tab"
              aria-pressed={filter === f.key}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
              <span className="ark-tab__count">{counts[f.key]}</span>
            </button>
          ))}
        </div>

        <div style={{ position: "relative", flex: "0 1 320px", minWidth: 220 }}>
          <SearchIcon
            width={16}
            height={16}
            aria-hidden="true"
            style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--ink-400)", pointerEvents: "none" }}
          />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by job title or department"
            aria-label="Search jobs by title or department"
            style={{ width: "100%", padding: "8px 12px 8px 34px", fontSize: "var(--text-sm)" }}
          />
        </div>
      </div>

      <div style={{ overflowX: "auto" }}>
        {/* Fixed layout with the short columns pinned, so Title takes the
            remainder and every row's Active, Status and action line up
            regardless of how long a title runs. The minimum is the pinned
            columns plus room for a full title: on a window too narrow for
            that, the card scrolls sideways rather than cutting every
            title short. */}
        <table className="ark-table ark-table--rows" style={{ tableLayout: "fixed", minWidth: 600 }}>
          <thead>
            <tr>
              {sortHeader("title", "Job Title")}
              {sortHeader("department", "Department", { width: "24%", className: "ark-hide-narrow" })}
              {sortHeader("active", "Active", {
                align: "center",
                width: 96,
                title: "Candidates currently in this job's pipeline",
              })}
              <th style={{ width: 150 }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((req) => {
              const editable = isEditable(req);
              const href = editable || lockedOpens ? hrefFor(req) : null;
              const label = (
                <>
                  {editable ? (
                    <PencilIcon width={14} height={14} className="ark-access__icon" aria-hidden="true" />
                  ) : (
                    <LockIcon width={14} height={14} className="ark-access__icon" aria-hidden="true" />
                  )}
                  {editable ? "Edit" : "Locked"}
                </>
              );
              return (
                <tr
                  key={req.id}
                  className={href ? undefined : "ark-tr-static"}
                  title={href ? undefined : lockedHint}
                  onClick={
                    href
                      ? (e) => {
                          // The link already navigated; don't push the
                          // same page onto history a second time.
                          if ((e.target as HTMLElement).closest("a")) return;
                          navigate(href);
                        }
                      : undefined
                  }
                >
                  <td>
                    <span style={{ display: "flex", alignItems: "center", gap: 11, minWidth: 0 }}>
                      <IdentityMark initials={initials(req.title)} color={colorFor(deptColors, req.department)} size="sm" />
                      <span style={{ minWidth: 0 }}>
                        <span
                          className="ark-truncate"
                          title={req.title}
                          style={{ display: "block", fontWeight: 650, letterSpacing: "var(--track-snug)", color: "var(--ink-900)" }}
                        >
                          {req.title}
                        </span>
                        {/* Stands in for the Department column once
                            that column is hidden on a narrow screen. */}
                        <span className="ark-truncate ark-only-narrow" style={{ fontSize: "var(--text-xs)", color: "var(--ink-600)", marginTop: 1 }}>
                          {req.department}
                        </span>
                      </span>
                    </span>
                  </td>
                  <td className="ark-hide-narrow">
                    <span className="ark-truncate" title={req.department} style={{ display: "block", color: "var(--ink-600)" }}>
                      {req.department}
                    </span>
                  </td>
                  <td
                    className="ark-num"
                    style={{
                      textAlign: "center",
                      fontWeight: 650,
                      color: req.active_candidate_count > 0 ? "var(--ink-900)" : "var(--ink-300)",
                    }}
                  >
                    {req.active_candidate_count || "–"}
                  </td>
                  <td>
                    {href ? (
                      <Link
                        to={href}
                        className={`ark-access${editable ? " ark-access--edit" : ""}`}
                        title={editable ? undefined : lockedHint}
                        aria-label={editable ? `Edit the ${req.title} ${subject}` : `Open the ${req.title} ${subject} (locked)`}
                      >
                        {label}
                        <ArrowRightIcon width={13} height={13} className="ark-access__go" aria-hidden="true" />
                      </Link>
                    ) : (
                      <span className="ark-access" title={lockedHint}>
                        {label}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}

            {rows.length === 0 && (
              <tr className="ark-tr-static">
                <td colSpan={4} style={{ padding: 0 }}>
                  <div className="ark-empty">
                    <span className="ark-empty__mark">
                      <SearchIcon width={20} height={20} />
                    </span>
                    <span className="ark-empty__title">
                      {q
                        ? `No ${filter === "all" ? "" : `${filter} `}jobs match “${query.trim()}”`
                        : filter === "editable"
                          ? "No editable jobs right now"
                          : "No locked jobs"}
                    </span>
                    <span className="ark-empty__body">
                      {q
                        ? "Try another title or department."
                        : filter === "editable"
                          ? "Every open job has active candidates. A job becomes editable again once nobody is active in its pipeline."
                          : "No job has active candidates yet, so every one can be edited."}
                    </span>
                    {(q || filter !== "all") && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => {
                          setQuery("");
                          setFilter("all");
                        }}
                        style={{ marginTop: 4 }}
                      >
                        Show all jobs
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
