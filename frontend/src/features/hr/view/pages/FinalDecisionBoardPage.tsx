import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { apiFetch, ApiError, downloadFile } from "../../../../shared/api/client";
import type { FinalDecisionBoardResponse } from "../../../../shared/api/pipeline";
import { AppShell } from "../components/AppShell";
import { Card } from "../../../../shared/ui/Card";
import { Button } from "../../../../shared/ui/Button";
import { ErrorState } from "../../../../shared/ui/ErrorState";
import { DownloadIcon } from "../../../../shared/ui/icons";
import { PageHeader } from "../../../../shared/ui/PageHeader";

/**
 * The Hierarchical Sequential Ranking (thesis 5.1.2.7) — the ranked
 * board HR Director reviews for the final hire call, sorted descending
 * by (VP, Dept, HR, skill match). Purely informational: hiring/rejecting
 * still happens from the Candidate Profile page's existing actions, not
 * here — this page never submits anything.
 *
 * There are no overall Final Score and Tier columns: the HR Director's
 * office could not confirm how the final assessment is
 * computed, so the board shows only the scores each stage recorded.
 */
export function FinalDecisionBoardPage() {
  const { id } = useParams<{ id: string }>();
  const requisitionId = Number(id);
  const { token } = useAuth();
  const [board, setBoard] = useState<FinalDecisionBoardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    apiFetch<FinalDecisionBoardResponse>(`/hr/requisitions/${requisitionId}/final-decision-board`, { token })
      .then(setBoard)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load."))
      .finally(() => setLoading(false));
  }, [requisitionId, token, reloadKey]);

  async function handleDownload() {
    if (!board) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      // The filename here is what the browser actually saves it as (see
      // downloadFile) -- the server's own Content-Disposition name is
      // for anyone who hits the endpoint directly, not this flow.
      await downloadFile(
        `/hr/requisitions/${requisitionId}/final-decision-board/export`,
        token,
        `Final Decision Board - ${board.job_title}.xlsx`,
        "Could not download the Excel export."
      );
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : "Could not download the Excel export.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <AppShell>
      {/* This board belongs to one job, and so does the pipeline it came
          from — `?job=` lands back on that opening rather than on
          whichever one the Pipelines page would pick for itself. */}
      <PageHeader
        above={
          <Link to={`/hr/pipelines?job=${requisitionId}`} className="ark-back">
            &larr; {board ? `${board.job_title} · HR Workflow` : "Back to HR Workflow"}
          </Link>
        }
        title={board ? `${board.job_title} · Final Decision Board` : "Final Decision Board"}
        info={{
          summary: "Every candidate who has cleared all three executive interview rounds, ranked by VP score first.",
          points: [
            "This board is purely informational.",
            "Hire or reject each candidate from their own Candidate Profile page.",
          ],
        }}
        actions={
          board &&
          board.entries.length > 0 && (
            <Button variant="secondary" onClick={handleDownload} disabled={downloading}>
              <DownloadIcon width={14} height={14} />
              {downloading ? "Preparing..." : "Download Excel"}
            </Button>
          )
        }
      />
      {downloadError && (
        <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "crimson", marginTop: 8 }}>{downloadError}</p>
      )}

      <div style={{ marginTop: 32 }}>
        {loading && <p style={{ fontFamily: "var(--arkive-font)", color: "var(--ink-600)" }}>Loading...</p>}
        {error && <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />}
      </div>

      {board && board.entries.length === 0 && (
        <Card padding={24}>
          <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", fontStyle: "italic", margin: 0 }}>
            No candidates have cleared all three executive interview rounds for this job yet.
          </p>
        </Card>
      )}

      {board && board.entries.length > 0 && (
        <Card padding={0} elevation="md" style={{ overflowX: "auto" }}>
          <table className="ark-table ark-table--dense">
            <thead>
              <tr>
                {["#", "Candidate", "HR", "Dept", "VP", "Exec Consensus", "Skill Match", "Exam %ile", "Rubric"].map((h) => (
                  <th key={h} style={{ textAlign: NUMERIC_COLUMNS.has(h) ? "right" : "left" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {board.entries.map((entry, index) => (
                <tr key={entry.application_id}>
                  <td className="ark-num" style={{ ...numCell, color: "var(--ink-600)" }}>{index + 1}</td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <Link to={`/hr/applications/${entry.application_id}`} style={{ color: "var(--accent)", fontWeight: 600, textDecoration: "none" }}>
                      {entry.applicant_name}
                    </Link>
                  </td>
                  <td className="ark-num" style={numCell}>{entry.hr_score.toFixed(1)}</td>
                  <td className="ark-num" style={numCell}>{entry.dept_score.toFixed(1)}</td>
                  <td className="ark-num" style={numCell}>{entry.vp_score.toFixed(1)}</td>
                  <td className="ark-num" style={numCell}>{entry.executive_consensus_score.toFixed(2)}</td>
                  <td className="ark-num" style={numCell}>{entry.skill_match_score != null ? `${entry.skill_match_score.toFixed(1)}%` : "–"}</td>
                  <td className="ark-num" style={numCell}>{entry.exam_percentile != null ? `${entry.exam_percentile.toFixed(1)}%` : "–"}</td>
                  <td className="ark-num" style={numCell}>{entry.interview_rubric_score != null ? entry.interview_rubric_score.toFixed(1) : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </AppShell>
  );
}

/** Scores are compared down a column, so they sit right-aligned in
 *  tabular figures — the decimal points line up and the eye can scan. */
const NUMERIC_COLUMNS = new Set(["#", "HR", "Dept", "VP", "Exec Consensus", "Skill Match", "Exam %ile", "Rubric"]);

const numCell: React.CSSProperties = { textAlign: "right", whiteSpace: "nowrap" };
