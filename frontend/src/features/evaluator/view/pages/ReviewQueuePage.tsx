import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { InterviewListItem } from "../../../../shared/api/evaluator";
import { EvaluatorAppShell } from "../components/EvaluatorAppShell";
import { useLiveRefresh } from "../../../../shared/hooks/useLiveRefresh";
import { Card } from "../../../../shared/ui/Card";
import { Tag } from "../../../../shared/ui/Tag";
import { Button } from "../../../../shared/ui/Button";
import { Avatar } from "../../../../shared/ui/Avatar";
import { ErrorState } from "../../../../shared/ui/ErrorState";
import { CheckIcon } from "../../../../shared/ui/icons";
import { PageHeader } from "../../../../shared/ui/PageHeader";

export function ReviewQueuePage() {
  const { token } = useAuth();
  const [interviews, setInterviews] = useState<InterviewListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  // See hooks/useLiveRefresh — `silent` skips the loading flag (which
  // hides the queue) and keeps its errors quiet, so a background refresh
  // can never blank or error out a screen someone is watching.
  function loadInterviews(options: { silent?: boolean } = {}) {
    if (!options.silent) {
      setLoading(true);
      setError(null);
    }
    apiFetch<InterviewListItem[]>("/evaluator/interviews", { token })
      .then(setInterviews)
      .catch((err) => {
        if (!options.silent) setError(err instanceof ApiError ? err.message : "Failed to load.");
      })
      .finally(() => {
        if (!options.silent) setLoading(false);
      });
  }

  useEffect(() => {
    loadInterviews();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, reloadKey]);

  // No gate: this page is a read-only list, so there is no in-progress
  // input for a refresh to overwrite. It is also the screen where HR
  // assigning an interview has to show up on its own.
  useLiveRefresh(() => loadInterviews({ silent: true }));

  // Three states, because "assigned to me" and "ready for me to act on"
  // are not the same thing — which is the whole of the bug this page
  // had. HR assigns the panel up front, so an evaluator is assigned to
  // rounds the candidate has not reached yet; those must be visible
  // (they were announced by a notification) without pretending they can
  // be evaluated now.
  //   awaiting  — the candidate is on this round, has confirmed the
  //               interview time, and there is no scorecard yet. The
  //               only state with a form to fill in.
  //   waiting   — the candidate is on this round but no time is
  //               confirmed yet, so the form stays locked. The
  //               evaluator's part is their free
  //               times, on the interview's page.
  //   upcoming  — assigned, but the candidate has not reached this round
  //               (`pending`). Shown, not actionable.
  //   done      — a scorecard is in, or the round was closed without one
  //               (skipped, or completed past). Nothing left to do.
  const inProgress = interviews.filter((i) => i.status === "in_progress" && !i.already_evaluated);
  const awaiting = inProgress.filter((i) => i.schedule_confirmed);
  const waiting = inProgress.filter((i) => !i.schedule_confirmed);
  const upcoming = interviews.filter((i) => i.status === "pending");
  const done = interviews.filter(
    (i) => i.already_evaluated || (i.status !== "in_progress" && i.status !== "pending")
  );

  return (
    <EvaluatorAppShell>
      <PageHeader
        title="Review Queue"
        description={loading ? (
          "Loading your assigned interviews..."
        ) : awaiting.length > 0 ? (
          <>
            You have <strong style={{ color: "var(--accent)" }}>{awaiting.length}</strong> interview{awaiting.length === 1 ? "" : "s"}{" "}
            awaiting your evaluation
            {waiting.length > 0 && <>, {waiting.length} waiting for a confirmed time</>}
            {upcoming.length > 0 && <>, and {upcoming.length} more still to come</>}.
          </>
        ) : waiting.length > 0 ? (
          <>
            Nothing to evaluate right now: {waiting.length} interview{waiting.length === 1 ? " is" : "s are"} waiting
            for the applicant to confirm a time.
          </>
        ) : upcoming.length > 0 ? (
          <>
            Nothing to evaluate right now: {upcoming.length} assigned interview{upcoming.length === 1 ? "" : "s"}{" "}
            {upcoming.length === 1 ? "is" : "are"} waiting for the candidate to reach that round.
          </>
        ) : (
          "You're all caught up: no interviews awaiting evaluation."
        )}
      />

      {error && <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />}

      {!loading && !error && interviews.length === 0 && (
        <Card>
          <p style={{ fontFamily: "var(--arkive-font)", color: "var(--ink-400)", fontStyle: "italic", margin: 0 }}>
            No interviews assigned to you yet.
          </p>
        </Card>
      )}

      {!loading && !error && interviews.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
          {/* Awaiting first — the only section with anything to do. Then
              upcoming, so an evaluator can see who is coming and is not
              left wondering why a notification named someone who is not
              in the list. Done last, for reference. */}
          <QueueSection
            title="Awaiting your evaluation"
            interviews={awaiting}
            emptyHint={
              waiting.length > 0 || upcoming.length > 0
                ? "No scorecards are waiting on you. Your other interviews are listed below."
                : undefined
            }
            variant="awaiting"
          />
          {waiting.length > 0 && (
            <QueueSection
              title="Waiting for schedule"
              subtitle="The candidate is at this round, but hasn't confirmed an interview time yet. Add your free times on the interview's page so HR can send them; the form opens once a time is confirmed."
              interviews={waiting}
              variant="waiting"
            />
          )}
          {upcoming.length > 0 && (
            <QueueSection
              title="Upcoming"
              subtitle="Assigned to you, but the candidate hasn't reached this round yet. You'll be able to evaluate once they do."
              interviews={upcoming}
              variant="upcoming"
            />
          )}
          {done.length > 0 && (
            <QueueSection title="Completed" interviews={done} variant="done" />
          )}
        </div>
      )}
    </EvaluatorAppShell>
  );
}

type SectionVariant = "awaiting" | "waiting" | "upcoming" | "done";

function QueueSection({
  title,
  subtitle,
  interviews,
  emptyHint,
  variant,
}: {
  title: string;
  subtitle?: string;
  interviews: InterviewListItem[];
  emptyHint?: string;
  variant: SectionVariant;
}) {
  if (interviews.length === 0 && !emptyHint) return null;
  return (
    <section>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 4 }}>
        <h2 style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", fontWeight: 700, color: "var(--ink-900)", margin: 0 }}>
          {title}
        </h2>
        <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-400)", fontWeight: 600 }}>
          {interviews.length}
        </span>
      </div>
      {subtitle && (
        <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", margin: "0 0 12px", maxWidth: 620, lineHeight: 1.5 }}>
          {subtitle}
        </p>
      )}
      {interviews.length === 0 ? (
        /* A designed empty state, not a stubbed one. This is the *first*
           thing an evaluator with a clear queue sees, and a grey italic
           sentence in a big empty card reads as something failing to
           load. An icon, a plain statement of the good news, and where to
           look next — the mark is the same check the completed rows use,
           so the page agrees with itself. */
        <Card padding={0}>
          <div className="ark-empty">
            <span className="ark-empty__mark" style={{ background: "var(--success-bg)", color: "var(--success-text)" }}>
              <CheckIcon width={20} height={20} />
            </span>
            <span className="ark-empty__title">You&rsquo;re all caught up</span>
            <span className="ark-empty__body">{emptyHint}</span>
          </div>
        </Card>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: subtitle ? 0 : 8 }}>
          {interviews.map((interview) => (
            <QueueRow key={interview.stage_instance_id} interview={interview} variant={variant} />
          ))}
        </div>
      )}
    </section>
  );
}

function QueueRow({ interview, variant }: { interview: InterviewListItem; variant: SectionVariant }) {
  const badge =
    variant === "upcoming"
      ? { label: "Upcoming", tone: "neutral" as const }
      : variant === "waiting"
      ? { label: "Waiting for Schedule", tone: "neutral" as const }
      : interview.already_evaluated
      ? { label: "Evaluated", tone: "green" as const }
      : variant === "done"
      ? { label: interview.status === "skipped" ? "Skipped" : "Closed", tone: "neutral" as const }
      : { label: "Awaiting Evaluation", tone: "amber" as const };

  return (
    <Card padding={20}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <Avatar name={interview.applicant_name} size={44} src={interview.applicant_avatar_url} />
          <div>
            <div style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-lg)", fontWeight: 700, color: "var(--ink-900)" }}>
              {interview.applicant_name}
            </div>
            <div style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", marginTop: 2 }}>
              Applying for: {interview.job_title} · {interview.stage_label}
            </div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <Tag tone={badge.tone} dot>
            {badge.label}
          </Tag>
          {/* An upcoming round can be opened (to see the candidate and the
              schedule) but not evaluated — so it reads "View", never
              "Review". "Review" is reserved for the one state where there
              is actually something to record. */}
          <Link to={`/evaluator/interviews/${interview.stage_instance_id}`} style={{ textDecoration: "none" }}>
            <Button variant={variant === "awaiting" && !interview.already_evaluated ? "primary" : "secondary"}>
              {variant === "awaiting" && !interview.already_evaluated ? "Review" : "View"}
            </Button>
          </Link>
        </div>
      </div>
    </Card>
  );
}
