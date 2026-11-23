import { useState } from "react";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { ApplicationDetail } from "../../../../shared/api/applicant";
import { Button } from "../../../../shared/ui/Button";
import { ConfirmDialog } from "../../../../shared/ui/ConfirmDialog";
import { AlertIcon, CheckIcon } from "../../../../shared/ui/icons";
import { FinalSelectionScreen } from "./FinalSelectionScreen";

/** What a shortlisted candidate sees while their confirmation is still
 * owed.
 *
 * Shortlisting is the one point in this pipeline where the candidate is
 * asked rather than told. Every other stage happens *to* them — HR
 * schedules, evaluators score, the DFA advances. Here HR has picked them
 * and the question is whether they still want it, which weeks after
 * applying is a real question and not one the system should answer on
 * their behalf. Nobody is booked into an examination slot they never
 * agreed to sit.
 *
 * Three states, in the order a candidate meets them:
 *   unanswered — the news, then Continue / Withdraw.
 *   accepted   — never rendered; accepting advances the application to
 *                its next stage in the same request, so the next read is
 *                already on a different screen.
 *   declined   — never rendered; declining withdraws, and
 *                ApplicationStagePage short-circuits non-active statuses
 *                into its own closed-application line.
 *
 * A candidate shortlisted before this existed has no acceptance block at
 * all. That is deliberately not treated as "unanswered" — asking someone
 * to confirm a thing that was never asked of them, weeks later, would
 * invent a step that did not happen. Those fall through to the read-only
 * screen they have always had. */
export function ShortlistingResponseScreen({
  application,
  token,
  onUpdate,
}: {
  application: ApplicationDetail;
  token: string | null;
  onUpdate: (updated: ApplicationDetail) => void;
}) {
  const acceptance = application.shortlisting_acceptance;
  const [confirmingDecline, setConfirmingDecline] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Nothing to answer: not shortlisted, or shortlisted before this
  // existed. Either way the applicant is owed the same quiet
  // "we're reviewing" screen they had before.
  if (!acceptance || acceptance.response) {
    return <FinalSelectionScreen application={application} heading="Under Review" />;
  }

  // Whatever this job's workflow puts after Shortlisting -- an interview,
  // an exam, or nothing -- named from the stage list rather than assumed
  // to be an examination: workflows can run the exam *before*
  // Shortlisting.
  const stages = application.stage_instances;
  const shortlistingIndex = stages.findIndex((s) => s.stage_type === "shortlisting");
  const nextStageLabel = shortlistingIndex >= 0 ? stages[shortlistingIndex + 1]?.label ?? null : null;

  async function respond(action: "accept" | "decline") {
    setSubmitting(true);
    setError(null);
    try {
      const updated = await apiFetch<ApplicationDetail>(
        `/applicant/applications/${application.id}/shortlisting/${action}`,
        { method: "POST", token }
      );
      setConfirmingDecline(false);
      onUpdate(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not record your answer. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <div
        style={{
          display: "flex",
          gap: 12,
          alignItems: "flex-start",
          padding: "14px 16px",
          background: "var(--success-bg)",
          borderLeft: "3px solid var(--success-text)",
          borderRadius: "var(--radius-xs)",
        }}
      >
        <CheckIcon width={20} height={20} style={{ color: "var(--success-text)", flexShrink: 0, marginTop: 2 }} />
        <div>
          <h2
            style={{
              fontFamily: "var(--arkive-font)",
              fontSize: "var(--text-lg)",
              fontWeight: 700,
              color: "var(--success-text)",
              margin: 0,
            }}
          >
            You've been shortlisted
          </h2>
          <p
            style={{
              fontFamily: "var(--arkive-font)",
              fontSize: "var(--text-base)",
              color: "var(--ink-900)",
              margin: "6px 0 0",
              lineHeight: 1.6,
            }}
          >
            You've made the shortlist for <strong>{application.job_title}</strong>
            {nextStageLabel ? (
              <>
                , and your next stage is <strong>{nextStageLabel}</strong>
              </>
            ) : null}
            . Confirm below that you'd still like to go ahead, and HR will arrange the next step with you.
            Check the email we sent you for the full message from HR.
          </p>
        </div>
      </div>

      <div style={{ display: "flex", gap: 10, marginTop: 20, flexWrap: "wrap" }}>
        <Button variant="primary" disabled={submitting} onClick={() => respond("accept")}>
          {submitting ? "Working..." : "Yes, continue"}
        </Button>
        <Button variant="outline" disabled={submitting} onClick={() => setConfirmingDecline(true)}>
          Withdraw my application
        </Button>
      </div>

      {error && (
        <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "crimson", marginTop: 12 }}>
          {error}
        </p>
      )}

      <ConfirmDialog
        open={confirmingDecline}
        title="Withdraw your application?"
        description={`This closes your application for ${application.job_title}.`}
        confirmLabel="Withdraw Application"
        confirmVariant="danger"
        confirming={submitting}
        onCancel={() => setConfirmingDecline(false)}
        onConfirm={() => respond("decline")}
      >
        {/* Said plainly, before the press, because there is no undo — the
            same warning the Cancel Application flow gives, since this
            reaches exactly the same terminal state. */}
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
          <span
            style={{
              fontFamily: "var(--arkive-font)",
              fontSize: "var(--text-sm)",
              color: "var(--ink-900)",
              lineHeight: 1.5,
            }}
          >
            This cannot be undone, and you'll give up your place on the shortlist. You're welcome to apply
            for this role again in future, or to browse other openings now.
          </span>
        </div>
      </ConfirmDialog>
    </>
  );
}
