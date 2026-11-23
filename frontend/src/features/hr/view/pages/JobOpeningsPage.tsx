import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { RequisitionListItem, RequisitionStatus } from "../../../../shared/api/pipeline";
import { AppShell } from "../components/AppShell";
import { Card } from "../../../../shared/ui/Card";
import { Tag } from "../../../../shared/ui/Tag";
import { jobStatusTone } from "../../../../shared/lib/statusTags";
import { colorFor, departmentPalette, initials } from "../../../../shared/lib/identity";
import { IdentityMark } from "../../../../shared/ui/IdentityMark";
import { AlertIcon, BriefcaseIcon, ClockIcon, GlobeIcon, StopIcon, TrashIcon } from "../../../../shared/ui/icons";
import { JobStatusDialog } from "../components/JobStatusDialog";
import { statusActionLabel, todayISO } from "../../model/jobStatus";
import { Button } from "../../../../shared/ui/Button";
import { InfoTip } from "../../../../shared/ui/InfoTip";
import { RowMenu, type RowMenuItem } from "../../../../shared/ui/RowMenu";
import { ConfirmDialog } from "../../../../shared/ui/ConfirmDialog";
import { ErrorState } from "../../../../shared/ui/ErrorState";
import { PageHeader } from "../../../../shared/ui/PageHeader";

const STATUS_LABEL: Record<RequisitionStatus, string> = {
  open: "Open",
  draft: "Draft",
  closed: "Closed",
};

/** Whole days from an ISO date to today, counted the same (UTC) way
 *  todayISO() decides a deadline has passed, so the two never disagree. */
function daysSince(iso: string): number {
  return Math.round((Date.parse(todayISO()) - Date.parse(iso)) / 86_400_000);
}

function longDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** The card behind a passed deadline's ⓘ. Everything a new HR user asks
 *  on seeing "Open" and "Passed" on the same row, in the order they ask
 *  it: when was it, what does that mean for the job board, what does it
 *  mean for the people already applying — then why it still says Open
 *  and what to do about it. */
function PassedDeadlineDetails({ deadline, inPipeline }: { deadline: string; inPipeline: number }) {
  const days = daysSince(deadline);
  return (
    <>
      <div className="ark-tip__head">
        <ClockIcon width={15} height={15} style={{ color: "var(--warning-text)" }} />
        Application deadline passed
      </div>
      <dl className="ark-tip__facts">
        <dt>Deadline</dt>
        <dd>
          {longDate(deadline)}
          <small>{days === 1 ? "Yesterday" : `${days} days ago`}</small>
        </dd>
        <dt>Job board</dt>
        <dd>Hidden from applicants</dd>
        <dt>Pipeline</dt>
        <dd>
          {inPipeline > 0
            ? `${inPipeline} candidate${inPipeline === 1 ? "" : "s"}, unaffected`
            : "No one in progress"}
        </dd>
      </dl>
      <p className="ark-tip__note">
        It still says Open because it hasn't been closed. To take new applicants, close it and repost it
        with a later deadline.
      </p>
    </>
  );
}

/** The one place every job opening is visible, whatever its status.
 *
 * The Command Center's table reads /hr/dashboard/summary, which is
 * open-only by design — it answers "what is hiring right now." That left
 * two states with nowhere to live: a job saved as a draft could only be
 * reached by typing its URL and had no route to being published, and
 * nothing anywhere could take a live posting down. Both happen here.
 *
 * Closing is reversible and is not a delete: candidate_applications,
 * exam_slots and requisition_evaluators all point at a requisition, so a
 * hired candidate's record depends on the job outliving the hiring.
 *
 * Delete is offered alongside it for the postings HR does not want kept
 * — a duplicate, a typo'd title, a role cancelled before anyone saw it, a
 * finished round nobody will reopen. Closing those leaves them on this
 * list forever, and this list is the only place a draft can be reached,
 * so the clutter is permanent.
 *
 * Both live behind one "Actions" menu per row rather than as buttons side
 * by side. Side by side, a row was one or two buttons depending on its
 * pipeline, so the column never lined up, and the reversible action sat
 * a slip away from the permanent one. In the menu each entry carries a
 * line saying what it does, so someone new tells Close from Delete at
 * the moment of choosing.
 *
 * The gate is in_flight_candidate_count, not applications ever made:
 * anyone active or flagged is mid-pipeline and their next step is HR's.
 * Finished applications do not block it but ARE destroyed with the job,
 * so the confirmation names how many. Delete stays in the menu, greyed
 * with the reason, until the count is 0, and the API refuses regardless
 * of what the UI shows.
 *
 * Each row opens the job's own detail page (JobOpeningDetailPage), which
 * offers Close/Publish/Repost too — through the same JobStatusDialog —
 * but not Delete, which stays here alone. */
export function JobOpeningsPage() {
  const { token } = useAuth();
  const [jobs, setJobs] = useState<RequisitionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const navigate = useNavigate();
  const [changingStatus, setChangingStatus] = useState<RequisitionListItem | null>(null);
  const [deletingJob, setDeletingJob] = useState<RequisitionListItem | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    apiFetch<RequisitionListItem[]>("/hr/requisitions", { token })
      .then(setJobs)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load."))
      .finally(() => setLoading(false));
  }, [token, reloadKey]);

  async function deleteJob(job: RequisitionListItem) {
    setSubmitting(true);
    setActionError(null);
    try {
      await apiFetch<void>(`/hr/requisitions/${job.id}`, { method: "DELETE", token });
      setDeletingJob(null);
      setReloadKey((k) => k + 1);
    } catch (err) {
      // The API's own 409 names the job and the application count, which
      // is more use than anything this page could compose — surfaced as
      // written rather than replaced with a generic failure line.
      setActionError(err instanceof ApiError ? err.message : "Could not delete this job opening.");
    } finally {
      setSubmitting(false);
    }
  }

  /** Close for a live posting, Publish or Repost for one that isn't —
   *  never both, so the menu has a single way forward for the job. */
  function statusAction(job: RequisitionListItem): RowMenuItem {
    const Icon = job.status === "open" ? StopIcon : GlobeIcon;
    return {
      ...statusActionLabel(job.status),
      icon: <Icon width={15} height={15} style={{ color: "var(--ink-600)" }} />,
      onClick: () => setChangingStatus(job),
    };
  }

  /** The whole row opens the job's detail page. A click that began on
   *  something with its own job — the Actions menu, the deadline's ⓘ —
   *  is left to it; the menu's panel is portalled out of the table, so a
   *  click inside it arrives here through React without the row actually
   *  containing it in the page. */
  function openJobFromRow(e: React.MouseEvent<HTMLTableRowElement>, job: RequisitionListItem) {
    const target = e.target as HTMLElement;
    if (!e.currentTarget.contains(target) || target.closest("button, a, input")) return;
    navigate(`/hr/job-openings/${job.id}`);
  }

  /** Greyed with the reason rather than left out while anyone is still
   *  in the pipeline: every row's menu keeps the same shape, and a new
   *  user learns when Delete becomes available instead of wondering why
   *  some jobs have it. */
  function deleteAction(job: RequisitionListItem): RowMenuItem {
    const inFlight = job.in_flight_candidate_count;
    const icon = <TrashIcon width={15} height={15} />;
    if (inFlight > 0) {
      return {
        label: "Delete Job Opening",
        disabled: true,
        hint: `${inFlight} candidate${inFlight === 1 ? " is" : "s are"} still in the pipeline`,
        icon,
        separated: true,
      };
    }
    return {
      label: "Delete Job Opening",
      description: "Removes it for good. This can't be undone.",
      tone: "danger",
      icon,
      separated: true,
      onClick: () => { setActionError(null); setDeletingJob(job); },
    };
  }

  /** Same department hues as the Command Center and the pipeline rail —
   *  built from the full list so the mapping matches on every screen. */
  const deptColors = departmentPalette(jobs.map((j) => j.department));

  return (
    <AppShell>
      <PageHeader
        title="Job Openings"
        info={{
          summary: "Every posting, including drafts and closed ones.",
          points: [
            "Click a job to see its posting, hiring stages and questions.",
            "Closing a job takes it off the public board and stops new applications.",
            "Candidates already in a closed job's pipeline carry on as normal.",
            "A posting with nobody left in its pipeline can be deleted outright.",
          ],
        }}
        actions={
          <Link to="/hr/requisitions/new" style={{ textDecoration: "none" }}>
            <Button variant="primary">Create Job Opening</Button>
          </Link>
        }
      />

      {loading && <p style={{ fontFamily: "var(--arkive-font)", color: "var(--ink-600)" }}>Loading...</p>}
      {error && <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />}

      {!loading && !error && (
        <Card padding={0} elevation="md">
          <div style={{ overflowX: "auto" }}>
            {/* Fixed proportions rather than letting the browser size
                columns from content. Auto layout gave the title 45% of a
                1700px table and then stranded Deadline and Active a
                screen apart with nothing between them; the eye has to
                travel that gap on every row. Status, Deadline and Active
                are short, known-width values, so they are pinned narrow
                and pulled together at the end where they read as one
                group of facts about the posting. */}
            <table className="ark-table ark-table--rows" style={{ minWidth: 820, tableLayout: "fixed" }}>
              <colgroup>
                <col style={{ width: "30%" }} />
                <col style={{ width: "21%" }} />
                {/* the status tags' fixed width, at the table's narrowest */}
                <col style={{ width: "14%" }} />
                <col style={{ width: "15%" }} />
                <col style={{ width: "7%" }} />
                {/* one "Actions" button on every row, so this is sized
                    for it alone rather than for the widest pair */}
                <col style={{ width: "13%" }} />
              </colgroup>
              <thead>
                <tr>
                  <th>Job Title</th>
                  <th>Department</th>
                  <th className="ark-status-cell ark-status-cell--short">Status</th>
                  <th>Deadline</th>
                  <th style={{ textAlign: "right" }}>Active</th>
                  <th>
                    <span style={srOnly}>Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => {
                  const lapsed =
                    job.status === "open" && job.application_deadline != null && job.application_deadline < todayISO();
                  return (
                    <tr
                      key={job.id}
                      tabIndex={0}
                      aria-label={`Open ${job.title}`}
                      onClick={(e) => openJobFromRow(e, job)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && e.target === e.currentTarget) navigate(`/hr/job-openings/${job.id}`);
                      }}
                    >
                      <td>
                        <span style={{ display: "flex", alignItems: "center", gap: 11, minWidth: 0 }}>
                          <IdentityMark initials={initials(job.title)} color={colorFor(deptColors, job.department)} size="sm" />
                          <span
                            className="ark-truncate"
                            title={job.title}
                            style={{ fontWeight: 650, letterSpacing: "var(--track-snug)" }}
                          >
                            {job.title}
                          </span>
                        </span>
                      </td>
                      <td className="ark-truncate" style={{ color: "var(--ink-600)", fontSize: "var(--text-sm)" }}>{job.department}</td>
                      <td className="ark-status-cell ark-status-cell--short">
                        <Tag tone={jobStatusTone(job.status)} dot>
                          {STATUS_LABEL[job.status]}
                        </Tag>
                      </td>
                      <td
                        className="ark-num"
                        style={{
                          color: lapsed ? "var(--warning-text)" : job.application_deadline ? "var(--ink-600)" : "var(--ink-300)",
                          fontSize: "var(--text-sm)",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {/* An open job past its deadline is already invisible to
                            applicants; the dashboard still counts it as open, so
                            say so here rather than let it look live. One word
                            in the column, the date and what it means behind
                            the ⓘ, rather than one string to work out both
                            from. A closed or draft
                            job isn't taking applications anyway, so its old
                            date is just a date, not a warning. */}
                        {lapsed && job.application_deadline ? (
                          <InfoTip label="Passed">
                            <PassedDeadlineDetails deadline={job.application_deadline} inPipeline={job.active_candidate_count} />
                          </InfoTip>
                        ) : (
                          job.application_deadline ?? "–"
                        )}
                      </td>
                      <td
                        className="ark-num"
                        style={{
                          textAlign: "right",
                          fontWeight: 650,
                          color: job.active_candidate_count > 0 ? "var(--ink-900)" : "var(--ink-300)",
                        }}
                      >
                        {job.active_candidate_count || "–"}
                      </td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        <RowMenu
                          triggerLabel="Actions"
                          label={`Actions for ${job.title}`}
                          items={[statusAction(job), deleteAction(job)]}
                        />
                      </td>
                    </tr>
                  );
                })}
                {jobs.length === 0 && (
                  <tr>
                    <td colSpan={6} style={{ padding: 0 }}>
                      <div className="ark-empty">
                        <span className="ark-empty__mark">
                          <BriefcaseIcon width={20} height={20} />
                        </span>
                        <span className="ark-empty__title">No job openings yet</span>
                        <span className="ark-empty__body">
                          Create one to start a pipeline. You can save it as a draft and publish when it is ready.
                        </span>
                        <Link to="/hr/requisitions/new" style={{ textDecoration: "none", marginTop: 4 }}>
                          <Button variant="secondary" size="sm">Create Job Opening</Button>
                        </Link>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <JobStatusDialog
        job={changingStatus}
        token={token}
        onCancel={() => setChangingStatus(null)}
        onChanged={() => {
          setChangingStatus(null);
          setReloadKey((k) => k + 1);
        }}
      />

      <ConfirmDialog
        open={deletingJob != null}
        title={`Delete "${deletingJob?.title}"?`}
        description={
          deletingJob && deletingJob.application_count > 0
            ? `No one is working through this posting any more, but ${deletingJob.application_count} finished application${deletingJob.application_count === 1 ? "" : "s"} (rejected, withdrawn or hired) ${deletingJob.application_count === 1 ? "is" : "are"} attached to it.`
            : "No one has applied to this posting, so nothing is carried away with it."
        }
        confirmLabel="Delete Job Opening"
        confirmVariant="danger"
        confirming={submitting}
        onCancel={() => setDeletingJob(null)}
        onConfirm={() => deletingJob && deleteJob(deletingJob)}
      >
        <div
          style={{
            display: "flex",
            gap: 10,
            alignItems: "flex-start",
            marginTop: 14,
            padding: "11px 12px",
            background: "var(--warning-bg)",
            borderLeft: "3px solid var(--warning-text)",
            borderRadius: "var(--radius-xs)",
          }}
        >
          <AlertIcon width={17} height={17} style={{ color: "var(--warning-text)", flexShrink: 0, marginTop: 1 }} />
          <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-900)", lineHeight: 1.5 }}>
            This cannot be undone.{" "}
            {deletingJob && deletingJob.application_count > 0
              ? "Those applications are permanently deleted along with their resumes, documents, stage history and evaluations. The candidates lose this job from their own dashboards. "
              : ""}
            Its exam slots and assigned evaluator pool go too. If you might post this role again, close it
            instead: a closed job keeps everything and can be reposted.
          </span>
        </div>
        {actionError && <p style={{ color: "crimson", fontSize: "var(--text-sm)", marginTop: 12 }}>{actionError}</p>}
      </ConfirmDialog>
    </AppShell>
  );
}



/** Visually hidden, still announced — same treatment the Command Center's
 *  actions column gets. */
const srOnly: React.CSSProperties = {
  position: "absolute",
  width: 1,
  height: 1,
  overflow: "hidden",
  clip: "rect(0 0 0 0)",
  whiteSpace: "nowrap",
};
