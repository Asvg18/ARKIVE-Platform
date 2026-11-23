/**
 * Find Jobs, the applicant's full job browser: search and filters across
 * the top, the openings down the left, the chosen one in full on the right.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { ApplicantAppShell } from "../components/ApplicantAppShell";
import { ApiError, apiFetch } from "../../../../shared/api/client";
import type { ApplicationDetail } from "../../../../shared/api/applicant";
import type { JobListItem, JobListResponse } from "../../../../shared/api/public";
import { colorFor, departmentPalette } from "../../../../shared/lib/identity";
import { Button } from "../../../../shared/ui/Button";
import { ErrorState } from "../../../../shared/ui/ErrorState";
import { BriefcaseIcon, SearchIcon, XIcon } from "../../../../shared/ui/icons";
import { PageHeader } from "../../../../shared/ui/PageHeader";
import { DEADLINES, SORTS, matchesDeadline, type DeadlineKey, type SortKey } from "./applicant-jobs/jobListModel";
import { FilterSelect } from "./applicant-jobs/FilterSelect";
import { Listing } from "./applicant-jobs/Listing";
import { JobPanel } from "./applicant-jobs/JobPanel";

/** An application that still stands — a rejected or withdrawn one can be
 *  made again (after the cooldown), so it doesn't mark the job. */
const STILL_APPLIED = new Set(["active", "flagged", "hired"]);

const SEARCH_DEBOUNCE_MS = 300;

/** List beside detail, so comparing roles is a click rather than a dialog
 * opened and closed. Search and department go to the server; the deadline
 * filter, sort and "hide applied" work on the loaded list. A position
 * already applied to offers the application instead of a second Apply.
 * The filters live in the URL (?q=&department=&deadline=&sort=&job=), so
 * the homepage can hand its search across and a view can be bookmarked. */
export function ApplicantJobsPage() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const q = params.get("q") ?? "";
  const department = params.get("department");
  const sort: SortKey = (params.get("sort") as SortKey) in SORTS ? (params.get("sort") as SortKey) : "newest";
  const deadline: DeadlineKey =
    (params.get("deadline") as DeadlineKey) in DEADLINES ? (params.get("deadline") as DeadlineKey) : "any";
  const hideApplied = params.get("hide") === "applied";
  const selectedId = Number(params.get("job")) || null;

  // Replace, not push: refining a search is not a place Back should
  // step through one keystroke at a time.
  function setParam(key: string, value: string | null) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true }
    );
  }

  const [searchInput, setSearchInput] = useState(q);
  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchInput.trim() !== q) setParam("q", searchInput.trim() || null);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchInput]);

  const [jobs, setJobs] = useState<JobListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [departments, setDepartments] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  // Out-of-order responses: only the newest request may write.
  const latestRequest = useRef(0);

  useEffect(() => {
    const requestId = ++latestRequest.current;
    const search = new URLSearchParams({ limit: "100" });
    if (q) search.set("q", q);
    if (department) search.set("department", department);
    setBusy(true);
    setError(null);
    apiFetch<JobListResponse>(`/public/jobs?${search.toString()}`)
      .then((res) => {
        if (requestId !== latestRequest.current) return;
        setJobs(res.items);
        setTotal(res.total);
        setDepartments(res.departments);
      })
      .catch((err) => {
        if (requestId !== latestRequest.current) return;
        setError(err instanceof ApiError ? err.message : "Couldn't load positions.");
      })
      .finally(() => {
        if (requestId !== latestRequest.current) return;
        setBusy(false);
        setLoading(false);
      });
  }, [q, department, reloadKey]);

  const [applications, setApplications] = useState<ApplicationDetail[]>([]);
  useEffect(() => {
    apiFetch<ApplicationDetail[]>("/applicant/applications", { token })
      .then(setApplications)
      .catch(() => setApplications([]));
  }, [token]);

  const appliedByJob = useMemo(() => {
    const map = new Map<number, ApplicationDetail>();
    for (const application of applications) {
      if (STILL_APPLIED.has(application.status)) map.set(application.requisition_id, application);
    }
    return map;
  }, [applications]);

  const visible = useMemo(() => {
    const filtered = jobs.filter(
      (job) => matchesDeadline(job, deadline) && !(hideApplied && appliedByJob.has(job.id))
    );
    return [...filtered].sort((a, b) => {
      if (sort === "title") return a.title.localeCompare(b.title);
      if (sort === "closing") {
        // Soonest deadline first; open-until-filled last.
        const da = a.application_deadline ? new Date(a.application_deadline).getTime() : Infinity;
        const db = b.application_deadline ? new Date(b.application_deadline).getTime() : Infinity;
        return da - db;
      }
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
  }, [jobs, deadline, hideApplied, appliedByJob, sort]);

  const selected = visible.find((job) => job.id === selectedId) ?? visible[0] ?? null;
  const palette = useMemo(() => departmentPalette(departments), [departments]);
  const hasFilters = q !== "" || department !== null || deadline !== "any" || hideApplied;

  function clearFilters() {
    setSearchInput("");
    setParams(
      (prev) => {
        const next = new URLSearchParams();
        const sortKept = prev.get("sort");
        if (sortKept) next.set("sort", sortKept);
        return next;
      },
      { replace: true }
    );
  }

  const detailRef = useRef<HTMLDivElement>(null);
  function select(job: JobListItem) {
    setParam("job", String(job.id));
    // Stacked on a narrow screen, the detail is below the list — bring it up.
    if (window.matchMedia("(max-width: 1023px)").matches) {
      requestAnimationFrame(() => detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    }
  }

  return (
    <ApplicantAppShell wide>
      <PageHeader
        title="Find Jobs"
        description={
          loading ? undefined : `${total} open ${total === 1 ? "position" : "positions"}${department ? ` in ${department}` : ""}`
        }
        info={{
          summary: "Every open faculty and staff position at the university.",
          points: [
            "Positions you've already applied to are marked Applied, with a link to your application.",
            "Each role lists the stages its hiring runs through, so you know what's ahead before applying.",
          ],
        }}
      />

      <div className="ark-finder" role="search">
        <label className="ark-finder__search">
          <SearchIcon width={16} height={16} aria-hidden="true" />
          <span className="ark-visually-hidden">Search positions</span>
          <input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search by title, skill or keyword"
          />
          {searchInput && (
            <button type="button" className="ark-finder__clear" onClick={() => setSearchInput("")} aria-label="Clear search">
              <XIcon width={13} height={13} />
            </button>
          )}
        </label>

        <FilterSelect label="Department" value={department ?? ""} onChange={(v) => setParam("department", v || null)}>
          <option value="">All</option>
          {departments.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </FilterSelect>

        <FilterSelect label="Deadline" value={deadline} onChange={(v) => setParam("deadline", v === "any" ? null : v)}>
          {Object.entries(DEADLINES).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </FilterSelect>

        <FilterSelect label="Sort" value={sort} onChange={(v) => setParam("sort", v === "newest" ? null : v)}>
          {Object.entries(SORTS).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </FilterSelect>

      </div>

      {error && <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />}

      {!error && (
        <div className="ark-browse">
          <div className="ark-browse__list" data-busy={busy || undefined}>
            <div className="ark-browse__meta">
              <span>
                {loading ? (
                  "Loading positions…"
                ) : (
                  <>
                    <b>{visible.length}</b> {visible.length === 1 ? "position" : "positions"}
                    {q && <> for “{q}”</>} · {SORTS[sort].toLowerCase()}
                  </>
                )}
              </span>
              <span className="ark-browse__meta-end">
                {/* Beside the count it changes, since it filters this list. */}
                {appliedByJob.size > 0 && (
                  <label className="ark-finder__toggle">
                    <input
                      type="checkbox"
                      checked={hideApplied}
                      onChange={(e) => setParam("hide", e.target.checked ? "applied" : null)}
                    />
                    Hide applied
                  </label>
                )}
                {hasFilters && (
                  <button type="button" className="ark-go" onClick={clearFilters}>
                    Clear filters
                  </button>
                )}
              </span>
            </div>

            {visible.map((job) => (
              <Listing
                key={job.id}
                job={job}
                color={colorFor(palette, job.department)}
                applied={appliedByJob.has(job.id)}
                selected={selected?.id === job.id}
                onSelect={() => select(job)}
              />
            ))}

            {!loading && visible.length === 0 && (
              <div className="ark-browse__empty">
                <BriefcaseIcon width={24} height={24} aria-hidden="true" />
                <p className="ark-browse__empty-title">No positions match.</p>
                <p className="ark-browse__empty-body">Try another keyword, or clear the filters.</p>
                {hasFilters && (
                  <Button variant="secondary" onClick={clearFilters}>
                    Clear filters
                  </Button>
                )}
              </div>
            )}

            {total > jobs.length && (
              <p className="ark-browse__note">
                Showing the first {jobs.length} of {total}. Narrow your search to see the rest.
              </p>
            )}
          </div>

          <div className="ark-browse__detail" ref={detailRef}>
            {selected && (
              <JobPanel
                key={selected.id}
                job={selected}
                color={colorFor(palette, selected.department)}
                application={appliedByJob.get(selected.id) ?? null}
                onApplied={(created) => navigate(`/applicant/applications/${created.id}`)}
                onOpenApplication={(id) => navigate(`/applicant/applications/${id}`)}
              />
            )}
          </div>
        </div>
      )}
    </ApplicantAppShell>
  );
}
