import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { RequisitionDetail, RequisitionStatus } from "../../../../shared/api/pipeline";
import { jobStageLabel } from "../../../../shared/lib/stageLabels";
import { AppShell } from "../components/AppShell";
import { ExamSessionsPanel } from "../components/ExamSessionsPanel";
import { InterviewReportPanel } from "../components/InterviewReportPanel";
import { JobPostingPanel } from "../components/JobPostingPanel";
import { JobStatusDialog } from "../components/JobStatusDialog";
import { statusActionLabel, todayISO } from "../../model/jobStatus";
import { Tag } from "../../../../shared/ui/Tag";
import { jobStatusTone } from "../../../../shared/lib/statusTags";
import { Button } from "../../../../shared/ui/Button";
import { ErrorState } from "../../../../shared/ui/ErrorState";
import { ArrowRightIcon } from "../../../../shared/ui/icons";
import { PageHeader } from "../../../../shared/ui/PageHeader";

const STATUS_LABEL: Record<RequisitionStatus, string> = {
  open: "Open",
  draft: "Draft",
  closed: "Closed",
};

/** Where the posting's text is being read, if anywhere — so HR knows
 *  whether what they are looking at is live. */
const POSTING_NOTE: Record<RequisitionStatus, string> = {
  open: "What applicants read on the job board.",
  draft: "Applicants will read this once it's published.",
  closed: "Off the job board while this job is closed.",
};

function longDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** One job opening on its own page — reached by clicking its row on Job
 *  Openings.
 *
 *  The posting exactly as applicants read it (HR does not land on the
 *  public board), beside the two things that decide how its hiring runs
 *  (the stage sequence and the pre-screening questions), each with the
 *  door to the builder that changes it. Everything shown is the job's own record
 *  (GET /hr/requisitions/{id}). The posting itself is the one thing edited
 *  in place (JobPostingPanel), and only until someone applies — the same
 *  lock as the stage order.
 *
 *  Close/Publish/Repost are offered here through the same dialog the list
 *  uses. Delete is not: it stays on Job Openings alone, one door to an
 *  irreversible action. */
export function JobOpeningDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuth();
  const [job, setJob] = useState<RequisitionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [changingStatus, setChangingStatus] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);
    apiFetch<RequisitionDetail>(`/hr/requisitions/${id}`, { token })
      .then(setJob)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load this job opening."))
      .finally(() => setLoading(false));
  }, [id, token, reloadKey]);

  const locked = job != null && job.active_candidate_count > 0;
  const lapsed = job?.status === "open" && job.application_deadline != null && job.application_deadline < todayISO();
  const statusAction = job ? statusActionLabel(job.status) : null;

  return (
    <AppShell>
      <PageHeader
        above={
          <Link to="/hr/job-openings" className="ark-back">
            &larr; Job Openings
          </Link>
        }
        title={job?.title ?? "Job Opening"}
        description={job?.department}
        info={{
          summary: "One job opening: the posting applicants read, and how its hiring runs.",
          points: [
            "Edit the job posting here until someone applies. The match score measures applicants against it.",
            "Stages and questions are changed in their own builders, linked from each panel.",
            "For a job with an exam, Exam sessions holds the dates and times applicants can book.",
            "Once everyone in the interviews has finished, Interview results offers a printable ranking to preview or download.",
            "While anyone is active in this pipeline, the posting, the stage order and the questions are locked.",
            "To delete a job opening, use its Actions menu on Job Openings.",
          ],
        }}
        actions={
          job &&
          statusAction && (
            <>
              <Link to={`/hr/pipelines?job=${job.id}`} style={{ textDecoration: "none" }}>
                <Button variant="secondary">View in HR Workflow</Button>
              </Link>
              <Button
                variant={job.status === "open" ? "secondary" : "primary"}
                title={statusAction.description}
                onClick={() => setChangingStatus(true)}
              >
                {statusAction.label}
              </Button>
            </>
          )
        }
      />

      {loading && !job && <p style={{ fontFamily: "var(--arkive-font)", color: "var(--ink-600)" }}>Loading...</p>}
      {error && <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />}

      {job && !error && (
        <>
          <dl className="ark-summary">
            <div>
              <dt>Status</dt>
              <dd>
                <Tag tone={jobStatusTone(job.status)} dot>
                  {STATUS_LABEL[job.status]}
                </Tag>
              </dd>
            </div>
            <div>
              <dt>Application deadline</dt>
              <dd
                className="ark-num"
                style={{ color: lapsed ? "var(--warning-text)" : job.application_deadline ? undefined : "var(--ink-400)" }}
              >
                {/* An open job past its deadline is already hidden from
                    applicants while still counted as open — said here, as
                    on the list, so it doesn't pass for live. */}
                {job.application_deadline
                  ? `${longDate(job.application_deadline)}${lapsed ? " · passed" : ""}`
                  : "Not set"}
              </dd>
            </div>
            <div>
              <dt>Active candidates</dt>
              <dd className="ark-num">{job.active_candidate_count}</dd>
            </div>
          </dl>

          <div className="ark-detail-grid">
            <JobPostingPanel
              job={job}
              locked={locked}
              note={POSTING_NOTE[job.status]}
              token={token}
              onSaved={setJob}
            />

            <div className="ark-detail-grid__side">
              <InterviewReportPanel requisitionId={job.id} token={token} />

              <section className="ark-panel" aria-labelledby="job-stages-heading">
                <div className="ark-panel__head">
                  <div>
                    <h2 id="job-stages-heading" className="ark-panel__title">Hiring stages</h2>
                    {locked && <p className="ark-panel__sub">Order locked while candidates are active.</p>}
                  </div>
                  <span className="ark-panel__count">
                    {job.workflow_definition.length} {job.workflow_definition.length === 1 ? "stage" : "stages"}
                  </span>
                </div>
                <div className="ark-panel__body">
                  {job.workflow_definition.length > 0 ? (
                    <ol className="ark-numbered">
                      {job.workflow_definition.map((stage, i) => (
                        <li key={stage}>
                          <span className="ark-flow__n">{i + 1}</span>
                          <span>{jobStageLabel(stage, job)}</span>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="ark-panel__empty">No stages set.</p>
                  )}
                </div>
                <div className="ark-panel__foot">
                  <Link to={`/hr/requisitions/${job.id}/workflow`} className="ark-link-quiet">
                    Open in Workflow Builder <ArrowRightIcon width={14} height={14} />
                  </Link>
                </div>
              </section>

              <ExamSessionsPanel job={job} token={token} />

              <section className="ark-panel" aria-labelledby="job-questions-heading">
                <div className="ark-panel__head">
                  <div>
                    <h2 id="job-questions-heading" className="ark-panel__title">Pre-screening questions</h2>
                    {locked && <p className="ark-panel__sub">Fixed while candidates are active.</p>}
                  </div>
                  <span className="ark-panel__count">
                    {job.pre_screening_questions.length}{" "}
                    {job.pre_screening_questions.length === 1 ? "question" : "questions"}
                  </span>
                </div>
                <div className="ark-panel__body">
                  {job.pre_screening_questions.length > 0 ? (
                    <ol className="ark-numbered">
                      {job.pre_screening_questions.map((question, i) => (
                        <li key={question.id}>
                          <span className="ark-flow__n">{i + 1}</span>
                          <span>
                            {question.text}
                            {!question.required && <span className="ark-numbered__tag">Optional</span>}
                          </span>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="ark-panel__empty">No questions added.</p>
                  )}
                </div>
                <div className="ark-panel__foot">
                  <Link to={`/hr/requisitions/${job.id}/pre-screening-questions`} className="ark-link-quiet">
                    Open in Pre-Screening Questions <ArrowRightIcon width={14} height={14} />
                  </Link>
                </div>
              </section>
            </div>
          </div>
        </>
      )}

      <JobStatusDialog
        job={changingStatus ? job : null}
        token={token}
        onCancel={() => setChangingStatus(false)}
        onChanged={(updated) => {
          setChangingStatus(false);
          setJob(updated);
        }}
      />
    </AppShell>
  );
}
