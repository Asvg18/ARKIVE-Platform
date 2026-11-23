import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { ApplicationListItem, DashboardSummary, RequisitionListItem } from "../../../../shared/api/pipeline";
import { AppShell } from "../components/AppShell";
import { Button } from "../../../../shared/ui/Button";
import { ErrorState } from "../../../../shared/ui/ErrorState";
import { RowMenu } from "../../../../shared/ui/RowMenu";
import { TablePager } from "../../../../shared/ui/TablePager";
import { IdentityMark } from "../../../../shared/ui/IdentityMark";
import { Tag } from "../../../../shared/ui/Tag";
import { PageHeader } from "../../../../shared/ui/PageHeader";
import { InfoTip } from "../../../../shared/ui/InfoTip";
import { useLiveRefresh } from "../../../../shared/hooks/useLiveRefresh";
import { colorFor, departmentPalette, initials } from "../../../../shared/lib/identity";
import { paginate } from "../../../../shared/lib/paging";
import {
  ArrowRightIcon,
  BriefcaseIcon,
  CheckIcon,
  ChevronDownIcon,
  LayersIcon,
  LockIcon,
  PlusIcon,
  SearchIcon,
  SortIcon,
} from "../../../../shared/ui/icons";

type SortKey = "title" | "applications" | "active" | "deadline";
type Sort = { key: SortKey; dir: "asc" | "desc" };

const PAGE_SIZE = 10;
const collator = new Intl.Collator(undefined, { sensitivity: "base", numeric: true });

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function deadlinePassed(job: RequisitionListItem): boolean {
  return job.application_deadline != null && job.application_deadline < todayISO();
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

function compare(a: RequisitionListItem, b: RequisitionListItem, sort: Sort): number {
  let primary: number;
  switch (sort.key) {
    case "title":
      primary = collator.compare(a.title, b.title);
      break;
    case "applications":
      primary = a.application_count - b.application_count;
      break;
    case "active":
      primary = a.active_candidate_count - b.active_candidate_count;
      break;
    case "deadline":
      // No deadline sorts last either way: it is the absence of a date,
      // not a date later than every other.
      if (a.application_deadline === b.application_deadline) primary = 0;
      else if (a.application_deadline == null) return 1;
      else if (b.application_deadline == null) return -1;
      else primary = a.application_deadline < b.application_deadline ? -1 : 1;
      break;
  }
  // Ties fall back to the title so equal rows never shuffle between renders.
  const ordered = primary !== 0 ? primary : collator.compare(a.title, b.title);
  return sort.dir === "asc" ? ordered : -ordered;
}

/** The HR home screen: how hiring stands right now, then every open job.
 *
 * Laid out as a single stat strip rather than three floating cards, then
 * one table with its own search, sortable headings and pagination —
 * everything on the white page panel, divided by hairlines rather than
 * stacked in boxes.
 *
 * Three reads. /hr/dashboard/summary carries the headline counts, which
 * are computed server-side (pending final approvals exists nowhere else).
 * /hr/requisitions carries what the table needs and the summary does
 * not — deadline, total applications — the same list Job Openings shows,
 * narrowed here to what is open. /hr/applications supplies the one count
 * the summary lacks — candidates flagged at Skill Matching, who wait on
 * HR just as final decisions do — and is optional: if it fails, that
 * figure shows a dash and the rest of the page stands.
 * Every column is a real field; nothing on this screen is decorative. */
export function HrCommandCenterPage() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [allJobs, setAllJobs] = useState<RequisitionListItem[]>([]);
  const [applications, setApplications] = useState<ApplicationListItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [query, setQuery] = useState("");
  // Busiest first: the jobs with people moving through them are the
  // ones HR opens this screen to check on.
  const [sort, setSort] = useState<Sort>({ key: "active", dir: "desc" });
  const [page, setPage] = useState(0);

  /** Every read on the page. The first load shows skeletons; a silent one
   *  (the live refresh) swaps the numbers in place and, if a read fails,
   *  keeps the last good ones rather than blanking the screen. */
  function load(options: { silent?: boolean } = {}) {
    if (!options.silent) {
      setLoading(true);
      setError(null);
    }
    Promise.all([
      apiFetch<DashboardSummary>("/hr/dashboard/summary", { token }),
      apiFetch<RequisitionListItem[]>("/hr/requisitions", { token }),
    ])
      .then(([s, jobs]) => {
        setSummary(s);
        setAllJobs(jobs);
      })
      .catch((err) => {
        if (!options.silent) setError(err instanceof ApiError ? err.message : "Failed to load.");
      })
      .finally(() => {
        if (!options.silent) setLoading(false);
      });
    apiFetch<ApplicationListItem[]>("/hr/applications", { token })
      .then(setApplications)
      .catch(() => {
        if (!options.silent) setApplications(null);
      });
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, reloadKey]);

  // The page used to fetch once on open and never again, so a tab left
  // open showed the morning's numbers all day. Every 30 seconds while it
  // is on screen, and the moment the window regains focus. Nothing on
  // this page is a form, so there is no moment a refresh could interrupt.
  useLiveRefresh(() => load({ silent: true }), { intervalMs: 30_000 });

  const openJobs = useMemo(() => allJobs.filter((j) => j.status === "open"), [allJobs]);
  /** Built from every job, open or not — the same list the pipeline rail
   *  and Job Openings build theirs from, so a department keeps its hue
   *  from screen to screen. */
  const deptColors = departmentPalette(allJobs.map((j) => j.department));

  const q = query.trim().toLowerCase();
  const rows = useMemo(
    () =>
      openJobs
        .filter((j) => !q || j.title.toLowerCase().includes(q) || j.department.toLowerCase().includes(q))
        .sort((a, b) => compare(a, b, sort)),
    [openJobs, q, sort]
  );
  /** Open jobs whose deadline has passed are already hidden from the
   *  public board, so "open" overstates what is live. Counted apart. */
  const pastDeadline = openJobs.filter(deadlinePassed).length;
  const accepting = openJobs.length - pastDeadline;
  const flagged = applications?.filter((a) => a.status === "flagged").length;
  const waitingTotal = summary && flagged !== undefined ? summary.pending_final_approvals + flagged : undefined;
  const { pageCount, page: currentPage, visible } = paginate(rows, page, PAGE_SIZE);

  function toggleSort(key: SortKey) {
    setPage(0);
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
        : // Most first for a count, A–Z for a title, soonest first for a date.
          { key, dir: key === "applications" || key === "active" ? "desc" : "asc" }
    );
  }

  function sortHead(key: SortKey, label: string, title?: string) {
    const active = sort.key === key;
    return (
      <th aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"} title={title}>
        <button type="button" className="ark-dt__sort" data-active={active} onClick={() => toggleSort(key)}>
          {label}
          {active ? (
            <ChevronDownIcon
              width={13}
              height={13}
              aria-hidden="true"
              style={{ transform: sort.dir === "asc" ? "rotate(180deg)" : undefined }}
            />
          ) : (
            <SortIcon width={13} height={13} aria-hidden="true" />
          )}
        </button>
      </th>
    );
  }

  return (
    <AppShell>
      <PageHeader
        title="HR Dashboard"
        info={{ summary: "Overview of institutional hiring performance and active workflows." }}
        actions={
          <Link to="/hr/requisitions/new" style={{ textDecoration: "none" }}>
            <Button variant="primary">
              <PlusIcon width={15} height={15} aria-hidden="true" />
              Create Job Opening
            </Button>
          </Link>
        }
      />

      {error && <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />}

      {!error && (
        <>
          {/* What goes on top is what HR can act on, most urgent first:
              the people frozen until HR decides, then how many postings
              are actually live, then the size of the pipeline. Drafts and
              closed postings were here for a while; neither asks anything
              of HR today, and both are one click away on Job Openings. */}
          <section className="ark-stats" aria-label="Hiring at a glance">
            <div className="ark-stat">
              <div className="ark-stat__title-row">
                <p className="ark-stat__title">Waiting on You</p>
                <InfoTip ariaLabel="What is waiting on you" width={320} className="ark-tip--about">
                  <div className="ark-about">
                    <p className="ark-about__eyebrow">Waiting on you</p>
                    <dl className="ark-about__terms">
                      <dt className="ark-stat__status ark-stat__status--info">Final decision</dt>
                      <dd>Cleared every interview round. Hire or reject them from their Candidate Profile.</dd>
                      <dt className="ark-stat__status ark-stat__status--warning">Flagged</dt>
                      <dd>
                        Skill Matching rated them a weak fit. Their application is paused until you reject them or let
                        them continue, from their Candidate Profile.
                      </dd>
                    </dl>
                  </div>
                </InfoTip>
              </div>
              <div className="ark-stat__body">
                <div className="ark-stat__split">
                  <StatFigure value={summary?.pending_final_approvals} label="Final decision" tone="info" loading={loading} />
                  <StatFigure value={flagged} label="Flagged" tone="warning" loading={loading} />
                </div>
                {!loading && waitingTotal === 0 && (
                  <Tag tone="green">
                    <CheckIcon width={12} height={12} aria-hidden="true" />
                    All clear
                  </Tag>
                )}
              </div>
            </div>

            <div className="ark-stat">
              <p className="ark-stat__title">Accepting Applications</p>
              <div className="ark-stat__body">
                <StatValue value={loading ? undefined : accepting} loading={loading} />
                {!loading && pastDeadline > 0 && (
                  <Tag tone="amber" dot title="Still open, but hidden from applicants because their deadline has passed">
                    {pastDeadline} past deadline
                  </Tag>
                )}
              </div>
            </div>

            <div className="ark-stat">
              <p className="ark-stat__title">Active Candidates</p>
              <div className="ark-stat__body">
                <StatValue value={summary?.active_candidates} loading={loading} />
              </div>
            </div>
          </section>

          <section aria-labelledby="open-jobs-heading">
            <div className="ark-section-head">
              <h2 id="open-jobs-heading" className="ark-section-head__title">
                Active Job Openings
              </h2>
              <div className="ark-section-head__tools">
                <div className="ark-search" style={{ width: 260 }}>
                  <SearchIcon width={15} height={15} className="ark-search__icon" aria-hidden="true" />
                  <input
                    type="search"
                    value={query}
                    onChange={(e) => {
                      setQuery(e.target.value);
                      setPage(0);
                    }}
                    placeholder="Search jobs or departments"
                    aria-label="Search open jobs by title or department"
                    className="ark-search__input"
                  />
                </div>
              </div>
            </div>

            <div className="ark-dt-wrap">
              <div className="ark-dt-scroll">
                <table className="ark-dt ark-dt--rows" style={{ minWidth: 860 }}>
                  <colgroup>
                    <col style={{ width: "31%" }} />
                    <col style={{ width: "12%" }} />
                    <col style={{ width: "11%" }} />
                    <col style={{ width: "14%" }} />
                    {/* the status tags' fixed width, at the table's narrowest */}
                    <col style={{ width: "18%" }} />
                    <col style={{ width: "14%" }} />
                  </colgroup>
                  <thead>
                    <tr>
                      {sortHead("title", "Job title")}
                      {sortHead("applications", "Applications", "Every application made to this job, however it ended")}
                      {sortHead("active", "Active", "Candidates currently moving through this job's pipeline")}
                      {sortHead("deadline", "Deadline")}
                      <th className="ark-status-cell">Status</th>
                      <th style={{ textAlign: "right" }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading &&
                      Array.from({ length: 5 }, (_, i) => (
                        <tr key={`skeleton-${i}`} className="ark-dt__static" aria-hidden="true">
                          <td>
                            <span style={{ display: "flex", alignItems: "center", gap: 12 }}>
                              <span className="ark-skeleton" style={{ width: 32, height: 32, flexShrink: 0 }} />
                              <span style={{ flex: 1 }}>
                                <span className="ark-skeleton" style={{ display: "block", width: "60%", height: 12 }} />
                                <span className="ark-skeleton" style={{ display: "block", width: "35%", height: 10, marginTop: 6 }} />
                              </span>
                            </span>
                          </td>
                          {[40, 30, 70, 64, 90].map((w, j) => (
                            <td key={j}>
                              <span className="ark-skeleton" style={{ display: "block", width: w, height: 12, marginLeft: j === 4 ? "auto" : 0 }} />
                            </td>
                          ))}
                        </tr>
                      ))}

                    {!loading &&
                      visible.map((job) => {
                        // By id, not by title — `?job=` selects the opening
                        // on the Pipelines page.
                        const pipelineHref = `/hr/pipelines?job=${job.id}`;
                        const locked = job.active_candidate_count > 0;
                        const passed = deadlinePassed(job);
                        return (
                          <tr
                            key={job.id}
                            onClick={(e) => {
                              // The View link already navigated; don't push
                              // the same page onto history a second time.
                              if ((e.target as HTMLElement).closest("a")) return;
                              navigate(pipelineHref);
                            }}
                          >
                            <td>
                              {/* Same identity tile as the pipeline rail,
                                  so a department reads the same everywhere. */}
                              <span style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
                                <IdentityMark initials={initials(job.title)} color={colorFor(deptColors, job.department)} />
                                <span style={{ minWidth: 0 }}>
                                  <span className="ark-truncate ark-dt__primary" title={job.title}>
                                    {job.title}
                                  </span>
                                  <span className="ark-truncate ark-dt__secondary" title={job.department}>
                                    {job.department}
                                  </span>
                                </span>
                              </span>
                            </td>
                            <td className="ark-num">
                              {job.application_count || <span style={{ color: "var(--ink-300)" }}>–</span>}
                            </td>
                            <td className="ark-num" style={{ fontWeight: 600 }}>
                              {job.active_candidate_count || <span style={{ color: "var(--ink-300)", fontWeight: 400 }}>–</span>}
                            </td>
                            <td className="ark-num" style={{ color: job.application_deadline ? "var(--ink-900)" : "var(--ink-400)" }}>
                              {job.application_deadline ? shortDate(job.application_deadline) : "No deadline"}
                            </td>
                            <td className="ark-status-cell">
                              {/* An open job past its deadline is already hidden
                                  from applicants; it still counts as open, so
                                  say so rather than let it look live. */}
                              {passed ? (
                                <Tag tone="amber" dot>
                                  Deadline passed
                                </Tag>
                              ) : (
                                <Tag tone="green" dot>
                                  Accepting
                                </Tag>
                              )}
                            </td>
                            <td>
                              <span style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 4 }}>
                                <Link
                                  to={pipelineHref}
                                  className="ark-btn ark-btn--secondary ark-btn--sm"
                                  aria-label={`View ${job.title} in HR Workflow`}
                                  style={{ textDecoration: "none" }}
                                >
                                  View
                                  <ArrowRightIcon width={13} height={13} aria-hidden="true" />
                                </Link>
                                <RowMenu
                                  label={`More actions for ${job.title}`}
                                  items={[
                                    locked
                                      ? {
                                          label: "Edit Workflow",
                                          disabled: true,
                                          hint: "Locked while candidates are active",
                                          icon: <LockIcon width={15} height={15} />,
                                        }
                                      : {
                                          label: "Edit Workflow",
                                          to: `/hr/requisitions/${job.id}/workflow`,
                                          icon: <LayersIcon width={15} height={15} style={{ color: "var(--ink-600)" }} />,
                                        },
                                    {
                                      label: "Final Decision Board",
                                      to: `/hr/requisitions/${job.id}/final-decision-board`,
                                      icon: <CheckIcon width={15} height={15} style={{ color: "var(--ink-600)" }} />,
                                    },
                                  ]}
                                />
                              </span>
                            </td>
                          </tr>
                        );
                      })}

                    {!loading && rows.length === 0 && (
                      <tr className="ark-dt__static">
                        <td colSpan={6} style={{ padding: 0 }}>
                          <div className="ark-empty">
                            <span className="ark-empty__mark">
                              {q ? <SearchIcon width={20} height={20} /> : <BriefcaseIcon width={20} height={20} />}
                            </span>
                            <span className="ark-empty__title">
                              {q ? `No open jobs match “${query.trim()}”` : "No open requisitions"}
                            </span>
                            <span className="ark-empty__body">
                              {q
                                ? "Try another title or department."
                                : "Once you publish a job opening it appears here with its live candidate count."}
                            </span>
                            {q ? (
                              <Button variant="secondary" size="sm" onClick={() => setQuery("")} style={{ marginTop: 4 }}>
                                Clear search
                              </Button>
                            ) : (
                              <Link to="/hr/requisitions/new" style={{ textDecoration: "none", marginTop: 4 }}>
                                <Button variant="secondary" size="sm">Create Job Opening</Button>
                              </Link>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {!loading && (
              <TablePager total={rows.length} page={currentPage} pageCount={pageCount} noun="job" onPage={setPage} />
            )}
          </section>
        </>
      )}
    </AppShell>
  );
}

/** A card's headline number. */
function StatValue({ value, loading }: { value: number | undefined; loading: boolean }) {
  if (loading) return <span className="ark-skeleton ark-stat__skeleton" />;
  return <span className="ark-stat__value">{value ?? "–"}</span>;
}

/** One of the split card's figures: the number, and beneath it a dot and
 *  word in the colour of the status it counts. */
function StatFigure({
  value,
  label,
  tone,
  loading,
}: {
  /** Undefined when its read failed — shown as a dash, not a zero. */
  value: number | undefined;
  label: string;
  tone: "info" | "warning";
  loading: boolean;
}) {
  return (
    <div className="ark-stat__figure">
      {loading ? (
        <span className="ark-skeleton ark-stat__skeleton ark-stat__skeleton--sm" />
      ) : (
        <span className="ark-stat__figure-value">{value ?? "–"}</span>
      )}
      <span className={`ark-stat__status ark-stat__status--${tone}`}>{label}</span>
    </div>
  );
}
