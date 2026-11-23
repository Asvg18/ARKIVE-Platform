import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { ApplicationDetail } from "../../../../shared/api/applicant";
import { ApplicationJourney } from "../components/ApplicationJourney";
import { APPLICANT_STATUS_LABELS } from "../../../../shared/lib/stageLabels";
import { ApplicantAppShell } from "../components/ApplicantAppShell";
import { useLiveRefresh } from "../../../../shared/hooks/useLiveRefresh";
import { Card } from "../../../../shared/ui/Card";
import { Tag } from "../../../../shared/ui/Tag";
import { applicationStatusTone } from "../../../../shared/lib/statusTags";
import { Button } from "../../../../shared/ui/Button";
import { ErrorState } from "../../../../shared/ui/ErrorState";
import { BriefcaseIcon } from "../../../../shared/ui/icons";
import { PageHeader } from "../../../../shared/ui/PageHeader";

export function ApplicantDashboardPage() {
  const { token } = useAuth();
  const [applications, setApplications] = useState<ApplicationDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [firstName, setFirstName] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  function loadApplications(options: { silent?: boolean } = {}) {
    if (!options.silent) {
      setLoading(true);
      setError(null);
    }
    apiFetch<ApplicationDetail[]>("/applicant/applications", { token })
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
    // The signed-in user's own name cannot change underneath them, so it
    // is fetched once here and deliberately left out of the refresh.
    apiFetch<{ full_name: string }>("/auth/me", { token })
      .then((me) => setFirstName(me.full_name.split(" ")[0]))
      .catch(() => setFirstName(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, reloadKey]);

  // Read-only list, so nothing to gate. This is where the applicant sees
  // HR advance them without having to reload.
  useLiveRefresh(() => loadApplications({ silent: true }));

  /** Three groups, because an applicant treats them as three different
   *  things: one they may need to act on, one that is good news and may
   *  still have onboarding attached, and one that is over. "flagged"
   *  counts as live — the applicant is still in the running, HR is
   *  simply reviewing by hand. */
  const live = applications.filter((a) => a.status === "active" || a.status === "flagged");
  const accepted = applications.filter((a) => a.status === "hired");
  const closed = applications.filter((a) => a.status === "rejected" || a.status === "withdrawn");

  return (
    <ApplicantAppShell>
      <PageHeader
        title={firstName ? `Welcome back, ${firstName}.` : "My Applications"}
        description="Track the status of every position you've applied to."
      />

      {loading && <p style={{ fontFamily: "var(--arkive-font)", color: "var(--ink-600)" }}>Loading...</p>}
      {error && <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />}

      {!loading && !error && applications.length === 0 && (
        <Card padding={40} style={{ textAlign: "center" }}>
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: "50%",
              background: "var(--accent-bg)",
              color: "var(--accent)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 16px",
            }}
          >
            <BriefcaseIcon width={26} height={26} />
          </div>
          <h2 style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xl)", fontWeight: 700, color: "var(--ink-900)", margin: 0 }}>
            You haven't applied to any positions yet.
          </h2>
          <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", marginTop: 8 }}>
            Explore open positions to begin your application journey.
          </p>
          <Link to="/applicant/jobs" style={{ textDecoration: "none" }}>
            <Button variant="primary" style={{ marginTop: 16 }}>
              Browse Open Positions
            </Button>
          </Link>
        </Card>
      )}

      {!loading && !error && applications.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
          {live.length > 0 && (
            <Section title="In progress" count={live.length} cards={live} />
          )}
          {accepted.length > 0 && (
            <Section
              title="Accepted"
              count={accepted.length}
              cards={accepted}
              hint="Congratulations. There may still be onboarding steps to finish."
            />
          )}
          {/* Closed applications used to sit in the same stack as live
              ones, so a withdrawn posting from months ago pushed the
              application you are actually working on below the fold.
              They are still here, still complete — just folded away,
              and reduced to a line each, because a closed application
              has nothing left to act on. */}
          {closed.length > 0 && <ClosedSection applications={closed} />}
        </div>
      )}
    </ApplicantAppShell>
  );
}

function Section({
  title,
  count,
  cards,
  hint,
}: {
  title: string;
  count: number;
  cards: ApplicationDetail[];
  hint?: string;
}) {
  return (
    <section>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: hint ? 4 : 12 }}>
        <span className="ark-meta" style={{ color: "var(--ink-600)" }}>{title}</span>
        <span className="ark-num ark-meta" style={{ color: "var(--ink-300)" }}>{count}</span>
      </div>
      {hint && (
        <p style={{ fontSize: "var(--text-sm)", color: "var(--ink-600)", margin: "0 0 12px" }}>{hint}</p>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {cards.map((application) => (
          <ApplicationCard key={application.id} application={application} />
        ))}
      </div>
    </section>
  );
}

/** A rejected or withdrawn application has nothing left to act on, so it
 * doesn't need a progress bar, a stage, or a button — just its name, its
 * outcome, and a way back in if they want to look. Collapsed by default:
 * the dashboard's job is the applications still in play. */
function ClosedSection({ applications }: { applications: ApplicationDetail[] }) {
  return (
    <details>
      <summary
        style={{
          cursor: "pointer",
          listStyle: "none",
          display: "inline-flex",
          alignItems: "center",
          gap: 7,
          fontSize: "var(--text-sm)",
          fontWeight: 600,
          color: "var(--ink-600)",
          padding: "4px 0",
        }}
      >
        <span className="ark-disclosure" aria-hidden="true" />
        Closed applications
        <span className="ark-num" style={{ color: "var(--ink-300)" }}>{applications.length}</span>
      </summary>
      <Card padding={0} style={{ marginTop: 12 }}>
        {applications.map((application, i) => (
          <Link
            key={application.id}
            to={`/applicant/applications/${application.id}`}
            className="ark-row"
            style={{
              textDecoration: "none",
              borderRadius: 0,
              borderTop: i === 0 ? "none" : "1px solid var(--hairline)",
              padding: "12px 16px",
            }}
          >
            <span style={{ flex: 1, minWidth: 0 }}>
              <span
                className="ark-truncate"
                style={{ display: "block", fontSize: "var(--text-sm)", fontWeight: 650, color: "var(--ink-700)" }}
              >
                {application.job_title}
              </span>
              <span
                className="ark-truncate"
                style={{ display: "block", fontSize: "var(--text-xs)", color: "var(--ink-400)", marginTop: 1 }}
              >
                {application.job_department}
              </span>
            </span>
            <Tag tone={applicationStatusTone(application.status)} dot>
              {APPLICANT_STATUS_LABELS[application.status] ?? application.status}
            </Tag>
          </Link>
        ))}
      </Card>
    </details>
  );
}

function ApplicationCard({ application }: { application: ApplicationDetail }) {
  return (
    <Card padding={24}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: "var(--text-xl)", fontWeight: 700, color: "var(--ink-950)", letterSpacing: "var(--track-tight)" }}>
            {application.job_title}
          </div>
          <div style={{ fontSize: "var(--text-sm)", color: "var(--ink-600)", marginTop: 2 }}>
            {application.job_department}
          </div>
        </div>
        <Tag tone={applicationStatusTone(application.status)} dot>
          {APPLICANT_STATUS_LABELS[application.status] ?? application.status}
        </Tag>
      </div>

      {/* The journey carries its own "Continue" on the row of the stage it
          applies to, rather than stranding a button at the bottom of the
          card away from the thing it acts on. */}
      <div style={{ marginTop: 18 }}>
        <ApplicationJourney application={application} compact />
      </div>

      {application.status === "flagged" && (
        <Link to={`/applicant/applications/${application.id}`} style={{ textDecoration: "none" }}>
          <Button variant="secondary" style={{ marginTop: 18 }}>
            View Review Details
          </Button>
        </Link>
      )}

      <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--surface-border)" }}>
        <Link
          to={`/applicant/applications/${application.id}/review`}
          className="ark-link-quiet"
          style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}
        >
          Review My Submission
        </Link>
      </div>
    </Card>
  );
}
