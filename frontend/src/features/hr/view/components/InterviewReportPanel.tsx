import { useEffect, useState } from "react";
import { apiFetch, ApiError, downloadFile, fetchFileBlobUrl } from "../../../../shared/api/client";
import { interviewReportPdfPath, type InterviewReport } from "../../../../shared/api/interviewReport";
import { Alert } from "../../../../shared/ui/Alert";
import { Button } from "../../../../shared/ui/Button";
import { Modal } from "../../../../shared/ui/Modal";
import { DownloadIcon, EyeIcon } from "../../../../shared/ui/icons";

/** How many of the ranking the panel lists before "and N more" — the
 *  panel is a glance; the PDF is the full record. */
const SHOWN = 5;

/** The interview results report on a job opening's page: the ranking of
 *  everyone who finished the interviews, as a printable PDF to preview or
 *  download.
 *
 *  The server decides readiness (services/interview_report.py) — ready
 *  once every candidate who reached the interviews has finished them — and
 *  this panel only says what it was told: the top of the ranking when
 *  ready, who the report is waiting on when not. Hidden entirely for a job
 *  with no interview rounds. */
export function InterviewReportPanel({ requisitionId, token }: { requisitionId: number; token: string | null }) {
  const [report, setReport] = useState<InterviewReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    apiFetch<InterviewReport>(`/hr/requisitions/${requisitionId}/interview-report`, { token })
      .then(setReport)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not check the interview results."));
  }, [requisitionId, token]);

  async function download() {
    if (!report) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      await downloadFile(interviewReportPdfPath(requisitionId), token, report.filename, "Could not download the report.");
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : "Could not download the report.");
    } finally {
      setDownloading(false);
    }
  }

  if (report && !report.has_interviews) return null;

  const ready = report?.ready ?? false;
  const shown = report?.entries.slice(0, SHOWN) ?? [];
  const more = (report?.entries.length ?? 0) - shown.length;

  return (
    <section className="ark-panel" aria-labelledby="interview-report-heading">
      <div className="ark-panel__head">
        <div>
          <h2 id="interview-report-heading" className="ark-panel__title">
            Interview results
          </h2>
          <p className="ark-panel__sub">
            {!report
              ? "Checking the interviews…"
              : ready
                ? "Every candidate in the interviews has finished."
                : "A printable ranking, ready once every candidate has finished the interviews."}
          </p>
        </div>
        {ready && report && <span className="ark-panel__count">{report.entries.length} ranked</span>}
      </div>

      <div className="ark-panel__body">
        {error && <Alert tone="danger" title={error} />}

        {report && ready && (
          <ol className="ark-numbered">
            {shown.map((entry) => (
              <li key={entry.application_id}>
                <span className="ark-flow__n">{entry.rank}</span>
                <span className="ark-numbered__grow">{entry.applicant_name}</span>
                <span className="ark-numbered__score">{entry.final_score.toFixed(2)}</span>
              </li>
            ))}
            {more > 0 && <li className="ark-numbered__more">and {more} more in the report</li>}
          </ol>
        )}

        {report && !ready && report.pending.length > 0 && (
          <>
            <p className="ark-report-waiting__label">Waiting on</p>
            <ul className="ark-report-waiting">
              {report.pending.map((p) => (
                <li key={p.application_id}>
                  <span className="ark-report-waiting__name">{p.applicant_name}</span>
                  <span className="ark-report-waiting__detail">{p.waiting_on.join(", ")}</span>
                </li>
              ))}
            </ul>
          </>
        )}

        {report && !ready && report.pending.length === 0 && report.excluded.length === 0 && (
          <p className="ark-panel__empty">No candidate has finished the interviews yet.</p>
        )}

        {report && !ready && report.pending.length === 0 && report.excluded.length > 0 && (
          <>
            <p className="ark-report-waiting__label">Reached the interviews but can't be ranked</p>
            <ul className="ark-report-waiting">
              {report.excluded.map((x, i) => (
                <li key={i}>
                  <span className="ark-report-waiting__name">{x.applicant_name}</span>
                  <span className="ark-report-waiting__detail">{x.reason}</span>
                </li>
              ))}
            </ul>
          </>
        )}

        {downloadError && <Alert tone="danger" title={downloadError} />}
      </div>

      {ready && (
        <div className="ark-panel__foot ark-panel__foot--actions">
          <Button variant="secondary" size="sm" onClick={() => setPreviewing(true)}>
            <EyeIcon width={14} height={14} aria-hidden="true" />
            Preview
          </Button>
          <Button variant="primary" size="sm" onClick={download} disabled={downloading}>
            <DownloadIcon width={14} height={14} aria-hidden="true" />
            {downloading ? "Preparing…" : "Download PDF"}
          </Button>
        </div>
      )}

      {previewing && report && (
        <ReportPreview report={report} token={token} onClose={() => setPreviewing(false)} />
      )}
    </section>
  );
}

/** The PDF itself, in the browser's own viewer, with the download beside
 *  it — the file is fetched once and the download saves that same copy. */
function ReportPreview({
  report,
  token,
  onClose,
}: {
  report: InterviewReport;
  token: string | null;
  onClose: () => void;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let created: string | null = null;
    fetchFileBlobUrl(interviewReportPdfPath(report.requisition_id), token, "Could not load the report.")
      .then((blobUrl) => {
        created = blobUrl;
        if (cancelled) URL.revokeObjectURL(blobUrl);
        else setUrl(blobUrl);
      })
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Could not load the report."));
    // an object URL pins the file in memory until revoked
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [report.requisition_id, token]);

  return (
    <Modal
      open
      width={960}
      title="Interview results report"
      sub={`${report.job_title} · ${report.entries.length} ranked`}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
          <div className="ark-wizard__foot-end">
            <Button variant="primary" disabled={!url} onClick={() => url && saveBlobUrl(url, report.filename)}>
              <DownloadIcon width={15} height={15} aria-hidden="true" />
              Download PDF
            </Button>
          </div>
        </>
      }
    >
      {error && <Alert tone="danger" title={error} />}
      {!error && !url && <p className="ark-panel__empty">Preparing the report…</p>}
      {url && <iframe className="ark-report-preview" src={url} title={`Interview results report for ${report.job_title}`} />}
    </Modal>
  );
}

/** Saves the copy already on screen, rather than fetching it again. Not
 *  revoked here: the preview still shows it, and revokes it on close. */
function saveBlobUrl(url: string, filename: string) {
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
}
