/**
 * The hiring pipelines, one job opening at a time: a rail of openings on
 * the left, and the chosen opening's candidates as a board or a list.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { departmentPalette } from "../../../../shared/lib/identity";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type {
  ApplicationListItem,
  RequisitionDetail,
  RequisitionListItem,
  StageType,
} from "../../../../shared/api/pipeline";
import { jobStageLabel } from "../../../../shared/lib/stageLabels";
import { useStageTransition, type StageMove } from "../../controller/useStageTransition";
import { AppShell } from "../components/AppShell";
import { PipelineBoard, type BoardStage } from "../components/PipelineBoard";
import { StageAdvanceDialog } from "../components/StageAdvanceDialog";
import { AdvanceDialog } from "../components/AdvanceDialog";
import { asksBeforeAdvancing } from "../../model/stageAdvance";
import { ShortlistDialog } from "../components/ShortlistDialog";
import { useLiveRefresh } from "../../../../shared/hooks/useLiveRefresh";
import { Card } from "../../../../shared/ui/Card";
import { Button } from "../../../../shared/ui/Button";
import { ErrorState } from "../../../../shared/ui/ErrorState";
import { InfoTip } from "../../../../shared/ui/InfoTip";
import { PageHeader } from "../../../../shared/ui/PageHeader";
import { CandidateList } from "./hr-pipeline/CandidateList";
import { JobSummaryCard } from "./hr-pipeline/JobSummaryCard";
import { OpeningsRail } from "./hr-pipeline/OpeningsRail";
import { isOpen, RAIL_SECTIONS, type JobEntry } from "./hr-pipeline/pipelineModel";

type PipelineView = "board" | "list";

const VIEW_STORAGE_KEY = "arkive.pipeline.view";

function readStoredView(): PipelineView {
  try {
    const stored = window.localStorage.getItem(VIEW_STORAGE_KEY);
    if (stored === "board" || stored === "list") return stored;
  } catch {
    // Private windows and blocked site data both throw on read.
  }
  return "board";
}

/** A move from this page: the candidate it is for, and whether it came
 *  from the list's Advance button or a drop on the board. */
interface PipelineMove extends StageMove {
  applicationId: number;
  application: ApplicationListItem;
  via: "advance" | "move";
}

/** The job is the frame, not a filter: the rail lists the openings by
 * status, each with its head count, and everything to the right belongs
 * to the one picked, so Board and List are two shapes of the same people.
 * The selection lives in `?job=`, so a link is to a pipeline and returning
 * from a candidate's profile returns to their opening. Search spans every
 * opening: it narrows the rail to openings with matches and shows how
 * many, so a name finds its job without leaving its context. */
export function HrPipelinePage() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [applications, setApplications] = useState<ApplicationListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rowError, setRowError] = useState<Record<number, string>>({});
  const [search, setSearch] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  // The opening on screen. Held in `?job=` so the Command Center and the
  // Workflow Builder can link straight to one, and so a candidate's
  // profile can send you back to the pipeline you came from rather than
  // to whichever one this page would have picked for itself.
  const [searchParams, setSearchParams] = useSearchParams();
  const jobParam = searchParams.get("job");
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);

  // `?q=` is how the top bar's search hands a term to this page. Read on
  // every change, so searching again from the top bar while already here
  // still takes effect; typing in the page's own box is left alone.
  const queryParam = searchParams.get("q");
  useEffect(() => {
    if (queryParam !== null) setSearch(queryParam);
  }, [queryParam]);

  const [view, setView] = useState<PipelineView>(readStoredView);
  const [shortlisting, setShortlisting] = useState(false);
  const railRef = useRef<HTMLDivElement | null>(null);
  const [jobs, setJobs] = useState<RequisitionListItem[]>([]);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [jobDetail, setJobDetail] = useState<RequisitionDetail | null>(null);
  const [moveError, setMoveError] = useState<{ stage: StageType; message: string } | null>(null);
  // A drag in progress on the board. Held here rather than inside it
  // because the thing that has to stop is this page's polling.
  const [boardDragging, setBoardDragging] = useState(false);
  // Every move, from the list's Advance button or a board drop. `via`
  // says which, so a confirmed move reports its refusal in the right place.
  const transition = useStageTransition<PipelineMove>(() => loadApplications());

  // `silent` is what makes background polling usable: the normal path
  // sets `loading`, which hides the whole pipeline below, so an unsilenced
  // refresh every few seconds would make it blink out of existence
  // repeatedly. A silent refresh also keeps its errors to itself — a
  // transient blip should leave the last good data on screen, not replace
  // a working pipeline with an error message.
  function loadApplications(options: { silent?: boolean } = {}) {
    if (!options.silent) {
      setLoading(true);
      setError(null);
    }
    apiFetch<ApplicationListItem[]>("/hr/applications", { token })
      .then(setApplications)
      .catch((err) => {
        if (!options.silent) setError(err instanceof ApiError ? err.message : "Failed to load.");
      })
      .finally(() => {
        if (!options.silent) setLoading(false);
      });
  }

  useEffect(() => {
    loadApplications();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, reloadKey]);

  // Every opening whatever its status — deliberately not the Command
  // Center's open-only /hr/dashboard/summary, which this page used to
  // read. A closed job's pipeline still has people in it (the hire that
  // closed it, for one), and a job with no candidates yet still deserves
  // to be findable here rather than only in the Job Openings list.
  useEffect(() => {
    apiFetch<RequisitionListItem[]>("/hr/requisitions", { token })
      .then((rows) => {
        setJobs(rows);
        setJobsError(null);
      })
      .catch((err) => setJobsError(err instanceof ApiError ? err.message : "Could not load job openings."));
  }, [token, reloadKey]);

  // The selected job's own workflow_definition is what the board's
  // columns are, and its per-job stage labels are what every stage name
  // on this screen is rendered through.
  useEffect(() => {
    if (selectedJobId == null) {
      setJobDetail(null);
      return;
    }
    let current = true;
    apiFetch<RequisitionDetail>(`/hr/requisitions/${selectedJobId}`, { token })
      .then((detail) => current && setJobDetail(detail))
      .catch(() => current && setJobDetail(null));
    return () => {
      current = false;
    };
  }, [selectedJobId, token]);

  // Paused mid-advance so a poll can't land between the transition
  // request and its own reload, briefly showing the pre-advance stage —
  // and paused mid-drag, because a refresh replaces the card array and
  // React re-renders the element under the cursor, at which point the
  // browser abandons the drag and the drop never fires. At an 8-second
  // interval that killed roughly one drag attempt in five.
  useLiveRefresh(() => loadApplications({ silent: true }), {
    enabled: transition.movingId === null && !boardDragging,
  });

  const query = search.trim().toLowerCase();

  /** Every opening with its candidates, filtered by the search. */
  const entries: JobEntry[] = useMemo(() => {
    const byJob = new Map<number, ApplicationListItem[]>();
    for (const application of applications) {
      const list = byJob.get(application.requisition_id);
      if (list) list.push(application);
      else byJob.set(application.requisition_id, [application]);
    }
    return jobs.map((job) => {
      const all = byJob.get(job.id) ?? [];
      // An opening whose own title or department matched shows its whole
      // pipeline; otherwise only the people whose names matched.
      const jobHit =
        !query || job.title.toLowerCase().includes(query) || job.department.toLowerCase().includes(query);
      const visible = jobHit
        ? all
        : all.filter((a) => a.applicant_name.toLowerCase().includes(query));
      return { job, all, visible };
    });
  }, [jobs, applications, query]);

  /** What the rail lists: everything, or — while searching — only the
   *  openings that matched, by title or by somebody in them. */
  const railSections = useMemo(
    () =>
      RAIL_SECTIONS.map((section) => ({
        ...section,
        entries: entries
          .filter((entry) => entry.job.status === section.status)
          .filter((entry) => !query || entry.visible.length > 0 || entry.job.title.toLowerCase().includes(query) || entry.job.department.toLowerCase().includes(query))
          // Busiest first: the pipeline with people in it is the one
          // being worked on. Alphabetical among equals so the rail does
          // not reshuffle itself as counts change.
          .sort(
            (a, b) =>
              b.all.filter(isOpen).length - a.all.filter(isOpen).length ||
              a.job.title.localeCompare(b.job.title)
          ),
      })).filter((section) => section.entries.length > 0),
    [entries, query]
  );

  const railEntries = useMemo(() => railSections.flatMap((s) => s.entries), [railSections]);
  /** Built from every job, not from the filtered rail — otherwise typing
   *  in the search box would re-rank the survivors and repaint the tiles
   *  mid-search, which is the one moment the colours are being used to
   *  find something. */
  const deptColors = useMemo(() => departmentPalette(jobs.map((j) => j.department)), [jobs]);
  /** The rail's order as a value rather than an array identity. The
   *  entries are rebuilt on every poll, so anything watching them fires
   *  every eight seconds; this changes only when the rail genuinely
   *  reorders — openings arriving, head counts loading, a search
   *  narrowing it. */
  const railOrder = useMemo(() => railEntries.map((entry) => entry.job.id).join(","), [railEntries]);

  // Seeding the selection. `?job=` wins; otherwise the opening at the top
  // of the rail — the busiest one — so what opens is what the eye lands
  // on. Deferred until the candidates have loaded, since the rail cannot
  // be ordered by head count before there are head counts.
  useEffect(() => {
    if (jobs.length === 0) return;
    const fromUrl = resolveJobParam(jobParam, jobs);
    if (fromUrl !== null) {
      setSelectedJobId(fromUrl);
      return;
    }
    if (loading) return;
    setSelectedJobId((current) =>
      current !== null && jobs.some((job) => job.id === current) ? current : railEntries[0]?.job.id ?? null
    );
  }, [jobs, jobParam, loading, railEntries]);

  function selectJob(id: number) {
    setSelectedJobId(id);
    setMoveError(null);
    const params = new URLSearchParams(searchParams);
    params.set("job", String(id));
    // Replace rather than push: picking an opening is choosing what to
    // look at, not travelling somewhere. Stacking every pick would make
    // Back mean "previous opening" instead of "back where I came from".
    setSearchParams(params, { replace: true });
  }

  /**
   * Brings the selected opening into view inside the rail.
   *
   * Arriving on `?job=` — from the Command Center, from a candidate's
   * profile, from a bookmark — can select an opening sitting below a
   * dozen others, and a highlight nobody can see is the same as no
   * highlight at all.
   *
   * Scrolls the rail and nothing else. `scrollIntoView` was the obvious
   * way to write this and the wrong one: it walks up the ancestors and
   * scrolls the *document* too, which on this page drags the whole shell
   * — nav, header, heading — off the top to reveal one list row.
   *
   * Keyed on the selection and on the rail's *order* — not on its
   * contents, which are rebuilt on every poll and would haul the rail
   * back to the selected row every eight seconds while someone was
   * reading further down it. The order matters because the rail sorts by
   * head count: it renders alphabetically for the moment before the
   * candidates land, and the re-sort that follows moves every row,
   * stranding a scroll position computed against the old one.
   */
  useEffect(() => {
    const rail = railRef.current;
    if (!rail || selectedJobId == null) return;
    const node = rail.querySelector<HTMLElement>(`[data-job-id="${selectedJobId}"]`);
    if (!node) return;
    const top = node.offsetTop;
    const bottom = top + node.offsetHeight;
    if (top < rail.scrollTop) rail.scrollTop = top - 8;
    else if (bottom > rail.scrollTop + rail.clientHeight) rail.scrollTop = bottom - rail.clientHeight + 8;
  }, [selectedJobId, railOrder]);

  /** Remembered across visits, because the trip out to a candidate's
   *  profile and back is the most common thing anyone does here — and
   *  landing back on the board every time when you had been working
   *  through the list is how this screen felt like it kept resetting
   *  itself. A view preference, not page state. */
  function chooseView(mode: PipelineView) {
    setView(mode);
    try {
      window.localStorage.setItem(VIEW_STORAGE_KEY, mode);
    } catch {
      // A browser refusing storage is not a reason to refuse the toggle.
    }
  }

  // A search that excludes the opening on screen would otherwise show a
  // narrowed rail beside an unnarrowed pipeline nobody asked about. Move
  // to the first opening that did match — usually the only one.
  useEffect(() => {
    if (!query || railEntries.length === 0) return;
    if (railEntries.some((entry) => entry.job.id === selectedJobId)) return;
    selectJob(railEntries[0].job.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, railEntries, selectedJobId]);

  const selected = entries.find((entry) => entry.job.id === selectedJobId) ?? null;

  /** The List tab's candidates, ranked by match_score within this one
   *  opening -- a rank only means something against the other candidates
   *  for the *same* job, which the List tab is already scoped to. Null
   *  scores (not through AI Pre-Screening yet) sort last and stay
   *  unranked rather than being numbered as if they were the weakest
   *  read; sorted here rather than in `entries` so the Board view, which
   *  reads from the same data, keeps its own (stage-grouped) order. */
  const rankedListRows = useMemo(() => {
    if (!selected) return [];
    const sorted = [...selected.visible].sort((a, b) => {
      if (a.match_score == null && b.match_score == null) return 0;
      if (a.match_score == null) return 1;
      if (b.match_score == null) return -1;
      return b.match_score - a.match_score;
    });
    let rank = 0;
    return sorted.map((application) => {
      if (application.match_score != null) rank += 1;
      return { application, rank: application.match_score != null ? rank : null };
    });
  }, [selected]);

  /** Everyone in this opening sitting on the shortlisting stage --
   *  the field the cutoff is drawn across. Read from `all`, not
   *  `visible`: a search filter is about what HR is looking at, and
   *  letting it change who gets a letter would be a trap. */
  const awaitingShortlisting = useMemo(
    () => (selected?.all ?? []).filter((a) => a.current_stage === "shortlisting" && a.status === "active"),
    [selected]
  );

  /** A stage in this job's own words — HR may have renamed its interview
   *  rounds and examinations, and those names are per-job data the static
   *  label map cannot know about. */
  function labelFor(stage: StageType | null): string {
    return jobStageLabel(stage, jobDetail);
  }

  function moveOf(application: ApplicationListItem, target: StageType, via: PipelineMove["via"]): PipelineMove {
    return { applicationId: application.id, application, target, via };
  }

  async function handleAdvance(application: ApplicationListItem) {
    if (!application.next_stage) return;
    if (asksBeforeAdvancing(application.next_stage)) {
      transition.askFirst(moveOf(application, application.next_stage, "advance"));
      return;
    }
    await requestAdvance(application, application.next_stage);
  }

  // A refusal is shown on the candidate's row. The stage gate's refusal is
  // not an error but a question, so the row stays clean and the dialog
  // carries the server's own list.
  async function requestAdvance(application: ApplicationListItem, target: StageType) {
    setRowError((prev) => ({ ...prev, [application.id]: "" }));
    await transition.send(moveOf(application, target, "advance"), "Transition failed.", (message) =>
      setRowError((prev) => ({ ...prev, [application.id]: message }))
    );
  }

  /**
   * A drop is a transition request like any other — the same endpoint the
   * list's "Advance" button calls. The DFA is never consulted on the
   * client: the board highlights the legal column as a hint, but the
   * server is what decides, and a refusal is rendered where the drop
   * happened.
   */
  async function handleMove(application: ApplicationListItem, target: StageType) {
    // Only the move the server offers is worth confirming -- a drop on
    // any other column is refused outright, and asking first would just
    // put a question in front of a "no".
    if (target === application.next_stage && asksBeforeAdvancing(target)) {
      transition.askFirst(moveOf(application, target, "move"));
      return;
    }
    await requestMove(application, target);
  }

  // A refusal is shown at the column. A drop onto a legal column that the
  // record is not ready for asks the same question the Advance button
  // does, deliberately not as a column refusal: the DFA's "no" is final
  // and belongs at the column, this one has an answer.
  async function requestMove(application: ApplicationListItem, target: StageType) {
    setMoveError(null);
    await transition.send(moveOf(application, target, "move"), "That move was rejected.", (message) =>
      setMoveError({ stage: target, message })
    );
  }

  const boardStages: BoardStage[] = (jobDetail?.workflow_definition ?? []).map((stage) => ({
    stage_type: stage,
    label: labelFor(stage),
  }));

  const totalOpen = applications.filter(isOpen).length;
  const matchedCandidates = entries.reduce((sum, entry) => sum + entry.visible.length, 0);
  const selectedOpen = selected ? selected.all.filter(isOpen).length : 0;
  const selectedClosed = selected ? selected.all.length - selectedOpen : 0;

  return (
    <AppShell>
      <PageHeader
        title="HR Workflow"
        description={query
          ? `${matchedCandidates} candidate${matchedCandidates === 1 ? "" : "s"} and ${railEntries.length} opening${
              railEntries.length === 1 ? "" : "s"
            } matching "${search.trim()}".`
          : `${totalOpen} candidate${totalOpen === 1 ? "" : "s"} still in play across ${jobs.length} opening${
              jobs.length === 1 ? "" : "s"
            }.`}
        info={{
          summary: "Pick an opening to work through its pipeline.",
          points: [
            "Board and List are two views of the same candidates.",
            "Search spans every opening and shows how many matches each one has.",
          ],
        }}
      />

      {error && <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />}
      {jobsError && <ErrorState message={jobsError} onRetry={() => setReloadKey((k) => k + 1)} />}

      <div style={{ display: "flex", alignItems: "flex-start", gap: 24 }}>
        {/* ── The openings ─────────────────────────────────────────── */}
        <OpeningsRail
          search={search}
          setSearch={setSearch}
          query={query}
          railRef={railRef}
          railSections={railSections}
          jobs={jobs}
          selectedJobId={selectedJobId}
          selectJob={selectJob}
          deptColors={deptColors}
        />

        {/* ── The selected opening's pipeline ───────────────────────── */}
        <section style={{ flex: 1, minWidth: 0 }}>
          {loading && !selected && (
            <p style={{ fontFamily: "var(--arkive-font)", color: "var(--ink-600)", margin: 0 }}>Loading...</p>
          )}

          {!loading && !selected && jobs.length > 0 && (
            <Card padding={24}>
              <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", margin: 0 }}>
                Pick a job opening on the left to see its pipeline.
              </p>
            </Card>
          )}

          {selected && (
            <>
              <JobSummaryCard
                selected={selected}
                deptColors={deptColors}
                selectedOpen={selectedOpen}
                selectedClosed={selectedClosed}
                jobDetail={jobDetail}
              />

              <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", margin: "20px 0 16px" }}>
                {/* role="tablist" as well as the styling: these two
                    genuinely are tabs over one set of people, and the
                    aria state is what .ark-tab keys its selected style
                    off — so the markup and the appearance cannot drift. */}
                <div className="ark-tabs" role="tablist" aria-label="Pipeline view">
                  {(["board", "list"] as const).map((mode) => (
                    <button
                      key={mode}
                      role="tab"
                      aria-selected={view === mode}
                      onClick={() => chooseView(mode)}
                      className="ark-tab"
                      style={{ textTransform: "capitalize" }}
                    >
                      {mode}
                    </button>
                  ))}
                </div>
                {/* Both views hold the same people; this says what each
                    one is *for*, since the difference is how you move
                    someone, not who you can see. */}
                <span style={{ fontSize: "var(--text-sm)", color: "var(--ink-600)" }}>
                  {view === "board"
                    ? "Where everyone stands. Drag a card onto the next stage to advance them."
                    : "Every candidate in this opening, with the stage they are up for next."}
                </span>
                {query && (
                  <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-400)", marginLeft: "auto" }}>
                    {selected.visible.length} of {selected.all.length} shown
                  </span>
                )}
                {/* The button is only offered when there is actually a field
                    to draw a line across — a permanently-present button for
                    a decision that cannot be made yet is the kind of thing
                    people learn to ignore. But leaving the spot empty made
                    the feature look missing on every other job, so the
                    two reasons it can't be used yet are said here instead,
                    as a word with the detail behind its ⓘ. Waits for this
                    job's own workflow, so it never flashes the wrong one. */}
                {awaitingShortlisting.length > 0 ? (
                  <Button
                    variant="primary"
                    size="sm"
                    style={{ marginLeft: query ? 12 : "auto" }}
                    onClick={() => setShortlisting(true)}
                  >
                    Shortlist Top Candidates ({awaitingShortlisting.length} waiting)
                  </Button>
                ) : (
                  jobDetail?.id === selected.job.id && (
                    <span style={{ marginLeft: query ? 12 : "auto", fontSize: "var(--text-sm)", color: "var(--ink-600)" }}>
                      {jobDetail.workflow_definition.includes("shortlisting") ? (
                        <InfoTip label="Shortlisting: nobody waiting" width={300}>
                          <div className="ark-tip__head">Shortlisting</div>
                          <p className="ark-tip__note">
                            Nobody in this job has reached the Shortlisting stage yet. Once someone does, a
                            Shortlist button appears here: you tick who goes on to the examination, and
                            write one email to those shortlisted and one to everyone else.
                          </p>
                        </InfoTip>
                      ) : (
                        <InfoTip label="No shortlisting stage" width={300}>
                          <div className="ark-tip__head">No shortlisting stage</div>
                          <p className="ark-tip__note">
                            This job's workflow has no Shortlisting stage, so its candidates move on without
                            a shortlist or the emails that go with one. Jobs set up before the stage existed
                            don't have it; new jobs on the Standard workflow do. It can be added in the
                            Workflow Builder while nobody is active in this pipeline.
                          </p>
                        </InfoTip>
                      )}
                    </span>
                  )
                )}
              </div>

              {selected.all.length === 0 ? (
                <Card padding={24}>
                  <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", margin: 0 }}>
                    Nobody has applied to this opening yet.
                  </p>
                </Card>
              ) : query && selected.visible.length === 0 ? (
                <Card padding={24}>
                  <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", margin: 0 }}>
                    No candidate in this opening matches "{search.trim()}".
                  </p>
                </Card>
              ) : view === "board" ? (
                boardStages.length === 0 ? (
                  <Card padding={24}>
                    <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", margin: 0 }}>
                      This job has no workflow defined, so it has no stages to lay out.{" "}
                      <Link to={`/hr/requisitions/${selected.job.id}/workflow`} style={{ color: "var(--accent)", fontWeight: 600 }}>
                        Build its workflow
                      </Link>{" "}
                      to see the board.
                    </p>
                  </Card>
                ) : (
                  <PipelineBoard
                    stages={boardStages}
                    applications={selected.visible}
                    onMove={handleMove}
                    moveError={moveError}
                    onDismissError={() => setMoveError(null)}
                    movingId={transition.movingId}
                    onDragActiveChange={setBoardDragging}
                  />
                )
              ) : (
                <CandidateList
                  rankedListRows={rankedListRows}
                  navigate={navigate}
                  labelFor={labelFor}
                  handleAdvance={handleAdvance}
                  movingId={transition.movingId}
                  rowError={rowError}
                />
              )}
            </>
          )}
        </section>
      </div>

      <AdvanceDialog
        open={transition.confirming !== null}
        candidateName={transition.confirming?.application.applicant_name ?? ""}
        fromStageLabel={transition.confirming ? labelFor(transition.confirming.application.current_stage) : ""}
        targetStageLabel={transition.confirming ? labelFor(transition.confirming.target) : ""}
        onConfirm={() => {
          const pending = transition.takeConfirming();
          if (!pending) return;
          if (pending.via === "move") void requestMove(pending.application, pending.target);
          else void requestAdvance(pending.application, pending.target);
        }}
        onCancel={transition.cancelConfirming}
      />

      {/* Opens only after the server has refused, and carries the
          server's own list — the rules are never re-derived here. */}
      <StageAdvanceDialog
        open={transition.pendingSkip !== null}
        candidateName={transition.pendingSkip?.application.applicant_name ?? ""}
        targetStageLabel={transition.pendingSkip ? labelFor(transition.pendingSkip.target) : ""}
        blockers={transition.pendingSkip?.blockers ?? []}
        message={transition.pendingSkip?.message ?? null}
        submitting={transition.skipSubmitting}
        error={transition.skipError}
        onConfirm={transition.confirmSkip}
        onCancel={transition.cancelSkip}
      />
      {shortlisting && selected && (
        <ShortlistDialog
          requisitionId={selected.job.id}
          jobTitle={selected.job.title}
          candidates={awaitingShortlisting}
          token={token}
          onClose={() => setShortlisting(false)}
          onDone={() => setReloadKey((k) => k + 1)}
        />
      )}
    </AppShell>
  );
}

/**
 * `?job=` as an opening.
 *
 * Normally its id. Older links — the Command Center's row, the Workflow
 * Builder's "Locked" button, anything a user bookmarked — carried the job
 * *title* instead, back when this parameter seeded a search box, so a
 * title is accepted too rather than silently selecting nothing.
 */
function resolveJobParam(param: string | null, jobs: RequisitionListItem[]): number | null {
  if (!param) return null;
  const asId = Number(param);
  if (Number.isInteger(asId) && asId > 0 && jobs.some((job) => job.id === asId)) return asId;
  const byTitle = jobs.find((job) => job.title.toLowerCase() === param.trim().toLowerCase());
  return byTitle?.id ?? null;
}


