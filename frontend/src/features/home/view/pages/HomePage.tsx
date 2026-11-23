import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { roleHomePath } from "../../../auth/model/roleHome";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import { colorFor, departmentPalette } from "../../../../shared/lib/identity";
import type { JobDetail, JobListItem, JobListResponse } from "../../../../shared/api/public";
import { Button } from "../../../../shared/ui/Button";
import { ErrorState } from "../../../../shared/ui/ErrorState";
import { ArrowRightIcon, BriefcaseIcon, SearchIcon, XIcon } from "../../../../shared/ui/icons";
import { Logo } from "../../../../shared/ui/Logo";
import { plural } from "../../model/jobDates";
import { HeroSignIn } from "../components/HeroSignIn";
import {
  ClosingCta,
  HiringProcess,
  SectionHead,
  SiteFooter,
  TransparencyBand,
} from "../components/landingSections";
import { DeptTab, JobCard, JobDetailModal } from "../components/jobCards";

/** How many openings the homepage shows. Past a handful the page stops
 * being a front door and becomes a list; the full list, with its own
 * search and filters, is the applicant portal's Find Jobs. */
const HOME_LIMIT = 6;

/** Typing shouldn't fire a request per keystroke. Long enough to coalesce a
 * burst of typing, short enough that results still feel immediate. */
const SEARCH_DEBOUNCE_MS = 300;

function scrollToId(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

/**
 * Public, unauthenticated job board — the homepage every applicant lands
 * on before they ever log in, and a page every logged-in role can browse
 * back to. Shows only what a candidate needs to decide whether to apply:
 * role, department, description, qualifications/requirements, deadline —
 * no internal pipeline detail, which belongs to the portals.
 *
 * Laid out on the pattern of a mature job board: a full hero (the
 * architectural plate shown whole and running up under a see-through
 * header), bold Inter headings over Inter text, then
 * the one promise this system makes that others don't (you can see
 * where you stand), the openings, and the process. Every
 * number on it is counted from the live listing — no "3 million job
 * seekers" of the kind these pages usually carry.
 */
export function HomePage() {
  const { user, token, logout } = useAuth();
  const navigate = useNavigate();
  const [jobs, setJobs] = useState<JobListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedJob, setSelectedJob] = useState<JobDetail | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  // Whether a request has *ever* succeeded. Without this, a retry after a
  // failed load clears the error and renders the still-empty jobs array,
  // so the page announces "0 open positions" — reporting an outage as an
  // empty job board, which is a different and much more alarming claim.
  const [hasLoaded, setHasLoaded] = useState(false);

  // `searchInput` tracks the field so typing stays responsive; `query` is the
  // debounced value the server actually sees.
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  // One department at a time, as tabs: "Computing" or everything. The
  // multi-select pills this replaced let two be ticked at once, which no
  // one arriving to browse a single department needed.
  const [department, setDepartment] = useState<string | null>(null);
  const [departments, setDepartments] = useState<string[]>([]);
  const [total, setTotal] = useState(0);
  // Every open job, from whichever response was unfiltered — what the
  // department tabs and the hero's counts are taken from, so they don't
  // shrink while someone searches.
  const [allJobs, setAllJobs] = useState<JobListItem[]>([]);
  const [unfilteredTotal, setUnfilteredTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  // Staff have no applicant portal to send them to, so for them "show
  // more" just opens the rest of the list here.
  const [showAll, setShowAll] = useState(false);

  const hasFilters = query.trim() !== "" || department !== null;

  useEffect(() => {
    const timer = setTimeout(() => setQuery(searchInput), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // The header is see-through over the hero, and takes a solid ground once
  // the page scrolls beneath it.
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Debounced filtering means several requests can be in flight at once, and
  // they can resolve out of order — a slow "a" landing after a fast "ab" would
  // show results for a query the user has already moved past. Only the newest
  // request is allowed to write to state.
  const latestRequest = useRef(0);

  useEffect(() => {
    const requestId = ++latestRequest.current;
    const trimmed = query.trim();
    const filtered = trimmed !== "" || department !== null;

    setBusy(true);
    setError(null);

    const params = new URLSearchParams();
    if (trimmed) params.set("q", trimmed);
    if (department) params.append("department", department);

    apiFetch<JobListResponse>(`/public/jobs?${params.toString()}`)
      .then((res) => {
        if (requestId !== latestRequest.current) return;
        setJobs(res.items);
        setTotal(res.total);
        setDepartments(res.departments);
        setHasLoaded(true);
        if (!filtered) {
          setUnfilteredTotal(res.total);
          setAllJobs(res.items);
        }
      })
      .catch((err) => {
        if (requestId !== latestRequest.current) return;
        setError(err instanceof ApiError ? err.message : "Failed to load jobs.");
      })
      .finally(() => {
        if (requestId !== latestRequest.current) return;
        setBusy(false);
        setLoading(false);
      });
  }, [query, department, reloadKey]);

  const palette = useMemo(() => departmentPalette(departments), [departments]);

  // Per-department counts are only claimed when the unfiltered page held
  // every open job; past the page size they would undercount, and a card
  // saying "2 open positions" for a department with 30 would be false.
  const countsComplete = allJobs.length > 0 && allJobs.length >= unfilteredTotal;
  const deptCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const job of allJobs) counts.set(job.department, (counts.get(job.department) ?? 0) + 1);
    return counts;
  }, [allJobs]);

  const popular = useMemo(
    () => [...departments].sort((a, b) => (deptCounts.get(b) ?? 0) - (deptCounts.get(a) ?? 0)).slice(0, 4),
    [departments, deptCounts]
  );

  const shownJobs = showAll ? jobs : jobs.slice(0, HOME_LIMIT);
  // The homepage's search, carried over so "browse all" opens on the
  // same results rather than starting again.
  const browseParams = new URLSearchParams();
  if (query.trim()) browseParams.set("q", query.trim());
  if (department) browseParams.set("department", department);
  const browseQuery = browseParams.toString();
  const browsePath = `/applicant/jobs${browseQuery ? `?${browseQuery}` : ""}`;

  // Applicants go to Find Jobs, which has the full list; staff have no
  // such page, so the rest opens here; visitors sign in first.
  function seeAll() {
    if (user?.role === "applicant") navigate(browsePath);
    else if (user) setShowAll(true);
    else navigate(`/login?next=${encodeURIComponent(browsePath)}`);
  }

  function clearFilters() {
    setSearchInput("");
    setQuery("");
    setDepartment(null);
  }

  function showDepartment(dept: string | null) {
    setDepartment(dept);
    scrollToId("openings");
  }

  function submitSearch(e: FormEvent) {
    e.preventDefault();
    // Skip the debounce: pressing Search means "now".
    setQuery(searchInput);
    scrollToId("openings");
  }

  function openJob(jobId: number) {
    setApplyError(null);
    apiFetch<JobDetail>(`/public/jobs/${jobId}`)
      .then(setSelectedJob)
      .catch((err) => setApplyError(err instanceof ApiError ? err.message : "Failed to load job."));
  }

  async function handleApply() {
    if (!selectedJob) return;

    if (!user) {
      navigate("/login");
      return;
    }
    if (user.role !== "applicant") {
      setApplyError("Only applicant accounts can apply to a position.");
      return;
    }

    setApplying(true);
    setApplyError(null);
    try {
      await apiFetch("/applications", {
        method: "POST",
        token,
        body: { requisition_id: selectedJob.id },
      });
      navigate("/applicant");
    } catch (err) {
      setApplyError(err instanceof ApiError ? err.message : "Could not submit application.");
    } finally {
      setApplying(false);
    }
  }

  return (
    <div className="ark-home">
      <header className="ark-home__nav" data-scrolled={scrolled || undefined}>
        <div className="ark-home__container ark-home__container--wide ark-home__nav-inner">
          <a href="#top" className="ark-home__brand" onClick={(e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
            <Logo size={32} />
            <span>ARKIVE</span>
          </a>

          {/* Anchors, not routes: every destination is a section of this
              page. Separate "Departments" or "Process" pages would mean
              inventing content the system does not have. */}
          <nav className="ark-home__links" aria-label="Job board">
            <a href="#openings">Open Positions</a>
            <a href="#process">Hiring Process</a>
            <a
              href={user ? roleHomePath(user.role) : "/login"}
              onClick={(e) => {
                e.preventDefault();
                navigate(user ? roleHomePath(user.role) : "/login");
              }}
            >
              Track Application
            </a>
          </nav>

          <div className="ark-home__nav-actions">
            {user ? (
              <>
                <Button variant="ghost" onClick={logout}>
                  Log out
                </Button>
                <Button variant="primary" onClick={() => navigate(roleHomePath(user.role))}>
                  Go to Dashboard
                </Button>
              </>
            ) : (
              <>
                <a
                  href="/signup"
                  className="ark-home__text-link"
                  onClick={(e) => {
                    e.preventDefault();
                    navigate("/signup");
                  }}
                >
                  Create account
                </a>
                <Button variant="primary" onClick={() => navigate("/login")}>
                  Sign In
                </Button>
              </>
            )}
          </div>
        </div>
      </header>

      <section id="top" className="ark-home__hero">
        <div className="ark-home__container ark-home__container--wide ark-home__hero-grid">
          <div className="ark-home__hero-copy">
            {unfilteredTotal > 0 && (
              <span className="ark-home__live">
                <span className="ark-home__pulse" aria-hidden="true" />
                Now hiring · {plural(unfilteredTotal, "open position")} across {plural(departments.length, "department")}
              </span>
            )}

            {/* One voice, two lines, one accent: the brand's Inter at its
                heaviest weight, tightly set, over Inter text at book
                weight — contrast of weight and size within the one family.
                The light line, bold line and gradient logotype it replaces
                read as three different speakers. */}
            <h1 className="ark-home__title">
              Begin your journey,
              <br />
              explore opportunities at <span className="ark-home__mark">ARKIVE</span>
            </h1>
            {/* The promise most job boards cannot make, and the one this
                system is built around — so it leads. */}
            <p className="ark-home__lede">
              Faculty and staff openings across the university. Every stage of your application is recorded, and you can
              see exactly where you stand, from the moment you upload to the final decision.
            </p>

            <form className="ark-home__search" onSubmit={submitSearch} role="search">
              <label className="ark-home__search-dept">
                <BriefcaseIcon width={16} height={16} aria-hidden="true" />
                <span className="ark-visually-hidden">Department</span>
                <select value={department ?? ""} onChange={(e) => setDepartment(e.target.value || null)}>
                  <option value="">All departments</option>
                  {departments.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </label>
              <label className="ark-home__search-query">
                <SearchIcon width={16} height={16} aria-hidden="true" />
                <span className="ark-visually-hidden">Keywords</span>
                <input
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  placeholder="Title, skill or keyword"
                />
                {searchInput && (
                  <button type="button" className="ark-home__search-clear" onClick={() => setSearchInput("")} aria-label="Clear search">
                    <XIcon width={13} height={13} />
                  </button>
                )}
              </label>
              <button type="submit" className="ark-btn ark-btn--primary ark-home__search-go">
                <SearchIcon width={15} height={15} aria-hidden="true" />
                Search
              </button>
            </form>

            {popular.length > 0 && (
              <div className="ark-home__popular">
                <span>Popular:</span>
                {popular.map((d) => (
                  <button key={d} type="button" onClick={() => showDepartment(d)}>
                    {d}
                  </button>
                ))}
              </div>
            )}
          </div>

          <HeroSignIn />
        </div>
      </section>

      <TransparencyBand role={user?.role ?? null} onNavigate={navigate} />

      <section id="openings" className="ark-home__section ark-home__section--ground">
        <div className="ark-home__container">
          <SectionHead
            eyebrow="Openings"
            title="Open positions"
            sub="Faculty and staff roles, each with the stages its hiring runs through."
          />

          {departments.length > 0 && (
            <div className="ark-home__tabs" role="tablist" aria-label="Filter by department">
              <DeptTab active={department === null} onClick={() => setDepartment(null)} count={countsComplete ? unfilteredTotal : undefined}>
                All
              </DeptTab>
              {departments.map((d) => (
                <DeptTab
                  key={d}
                  active={department === d}
                  onClick={() => setDepartment(department === d ? null : d)}
                  color={colorFor(palette, d)}
                  count={countsComplete ? deptCounts.get(d) : undefined}
                >
                  {d}
                </DeptTab>
              ))}
            </div>
          )}

          {!loading && !error && hasLoaded && (
            <div className="ark-home__result-bar">
              <span>
                {hasFilters
                  ? `${total} of ${plural(unfilteredTotal, "position")} match`
                  : plural(total, "open position")}
                {total > shownJobs.length && ` · showing ${shownJobs.length}`}
              </span>
              <span className="ark-home__result-actions">
                {hasFilters && (
                  <button type="button" className="ark-go" onClick={clearFilters}>
                    Clear filters
                  </button>
                )}
                {/* The way through to the rest, kept in this row rather
                    than a block beneath the grid that would cost a band of
                    height. A button, not a quiet link, so it isn't missed. */}
                {total > shownJobs.length && (
                  <button type="button" className="ark-home__see-all" onClick={seeAll}>
                    See all {total}
                    <ArrowRightIcon width={14} height={14} aria-hidden="true" />
                  </button>
                )}
              </span>
            </div>
          )}

          {/* `busy && !hasLoaded` covers the retry-after-failure case: there
              is nothing to dim yet, so say it is loading rather than render
              an empty grid. */}
          {(loading || (busy && !hasLoaded)) && <p className="ark-home__loading">Loading positions…</p>}
          {error && <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />}

          {!loading && !error && hasLoaded && (
            // Dimmed rather than unmounted while a filter request is in
            // flight: collapsing the grid on every keystroke makes the page
            // jump around under the user.
            <div className="ark-home__jobs" data-busy={busy || undefined}>
              {shownJobs.map((job) => (
                <JobCard key={job.id} job={job} color={colorFor(palette, job.department)} onOpen={() => openJob(job.id)} />
              ))}
              {jobs.length === 0 && (
                <div className="ark-home__empty">
                  <BriefcaseIcon width={26} height={26} aria-hidden="true" />
                  <p className="ark-home__empty-title">
                    {hasFilters ? "No positions match your search." : "No open positions right now."}
                  </p>
                  <p className="ark-home__empty-body">
                    {hasFilters ? "Try a different keyword, or clear your filters." : "Check back soon for new opportunities."}
                  </p>
                  {hasFilters && (
                    <Button variant="secondary" onClick={clearFilters} style={{ marginTop: 16 }}>
                      Clear filters
                    </Button>
                  )}
                </div>
              )}
            </div>
          )}

        </div>
      </section>

      <HiringProcess />
      <ClosingCta signedIn={user != null} onCreateAccount={() => navigate("/signup")} />
      <SiteFooter signedIn={user != null} onNavigate={navigate} dashboardPath={user ? roleHomePath(user.role) : null} />

      {selectedJob && (
        <JobDetailModal
          job={selectedJob}
          applyError={applyError}
          applying={applying}
          onApply={handleApply}
          onClose={() => setSelectedJob(null)}
        />
      )}
    </div>
  );
}
