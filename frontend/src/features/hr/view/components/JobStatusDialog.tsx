import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { RequisitionDetail } from "../../../../shared/api/pipeline";
import { ConfirmDialog } from "../../../../shared/ui/ConfirmDialog";
import { todayISO, type StatusJob } from "../../model/jobStatus";

/** Close, publish or repost one job opening, with the confirmation each
 *  needs. Shared by the Job Openings list and the job's detail page so
 *  the two can never word or gate the same change differently.
 *
 *  Delete is deliberately not here: it is offered on the Job Openings
 *  list only (one door to an irreversible action). */
export function JobStatusDialog({
  job,
  token,
  onCancel,
  onChanged,
}: {
  /** The job being changed; null keeps the dialog shut. */
  job: StatusJob | null;
  token: string | null;
  onCancel: () => void;
  onChanged: (updated: RequisitionDetail) => void;
}) {
  const [deadline, setDeadline] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!job) return;
    setError(null);
    // Prefill only a deadline that is still usable — reposting with one
    // that has already passed is refused by the API, and offering it back
    // as the default would walk HR straight into that refusal.
    const stored = job.application_deadline;
    setDeadline(stored && stored >= todayISO() ? stored : "");
  }, [job]);

  async function submit(body: Record<string, unknown>) {
    if (!job) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await apiFetch<RequisitionDetail>(`/hr/requisitions/${job.id}/status`, {
        method: "PATCH",
        token,
        body,
      });
      onChanged(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update this job opening.");
    } finally {
      setSubmitting(false);
    }
  }

  const errorLine = error && <p style={{ color: "crimson", fontSize: "var(--text-sm)", marginTop: 12 }}>{error}</p>;

  if (job?.status === "open") {
    return (
      <ConfirmDialog
        open
        title={`Close "${job.title}"?`}
        description={
          `It comes off the public job board immediately and no one new can apply. ` +
          `${job.active_candidate_count} candidate(s) already in this pipeline keep going, and you can repost it later.`
        }
        confirmLabel="Close Job Opening"
        confirming={submitting}
        onCancel={onCancel}
        onConfirm={() => submit({ status: "closed" })}
      >
        <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", margin: "12px 0 0", lineHeight: 1.55 }}>
          A closed job also stops being used in skill matching, so existing candidates' match scores
          against other open roles may shift.
        </p>
        {errorLine}
      </ConfirmDialog>
    );
  }

  return (
    <ConfirmDialog
      open={job != null}
      title={job?.status === "draft" ? `Publish "${job?.title}"?` : `Repost "${job?.title}"?`}
      description="Set the date applications close. It goes on the public job board straight away and starts accepting applicants."
      confirmLabel={job?.status === "draft" ? "Publish" : "Repost"}
      confirming={submitting}
      confirmDisabled={!deadline}
      onCancel={onCancel}
      onConfirm={() => submit({ status: "open", application_deadline: deadline })}
    >
      <label style={{ display: "block", fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--ink-900)", marginTop: 12 }}>
        Application deadline
        <input
          type="date"
          value={deadline}
          min={todayISO()}
          onChange={(e) => setDeadline(e.target.value)}
          style={{
            display: "block",
            marginTop: 6,
            padding: "8px 10px",
            border: "1px solid var(--surface-border)",
            borderRadius: "var(--radius)",
            fontFamily: "var(--arkive-font)",
            fontSize: "var(--text-base)",
            color: "var(--ink-900)",
          }}
        />
      </label>
      {errorLine}
    </ConfirmDialog>
  );
}
