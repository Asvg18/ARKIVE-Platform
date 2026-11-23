import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../../../../auth/controller/AuthContext";
import { apiFetch, ApiError } from "../../../../../shared/api/client";
import type { Pre201Package } from "../../../../../shared/api/pipeline";
import { openResumeFile } from "../../../../../shared/api/resume";
import { AppShell } from "../../components/AppShell";
import { SynthesisPanel } from "../../components/SynthesisPanel";
import { DecisionRecordPanel } from "../../components/DecisionRecordPanel";
import { Card } from "../../../../../shared/ui/Card";
import { Tag } from "../../../../../shared/ui/Tag";
import { Button } from "../../../../../shared/ui/Button";
import { ErrorState } from "../../../../../shared/ui/ErrorState";
import { SectionLabel } from "../../../../../shared/ui/SectionLabel";
import { DocumentIcon, DownloadIcon } from "../../../../../shared/ui/icons";
import { capitalize } from "./display";
import { PageHeader } from "../../../../../shared/ui/PageHeader";

/**
 * FR-11 — the Pre-201 digital file package: a compiled, read-only bundle
 * of a hired applicant's full record (thesis 5.1.1, Table 4). Only ever
 * reachable once HR has actually hired the candidate — see the "View
 * Pre-201 Package" link on CandidateProfilePage's closed-application bar.
 * Nothing on this page is editable; it's a record-keeping view, not
 * another pipeline action surface.
 */
export function Pre201PackagePage() {
  const { id } = useParams<{ id: string }>();
  const applicationId = Number(id);
  const { token } = useAuth();
  const [pkg, setPkg] = useState<Pre201Package | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    setError(null);
    apiFetch<Pre201Package>(`/hr/applications/${applicationId}/pre-201-package`, { token })
      .then(setPkg)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load."))
      .finally(() => setLoading(false));
  }, [applicationId, token, reloadKey]);

  return (
    <AppShell>
      <PageHeader
        above={
          <Link to={`/hr/applications/${applicationId}`} className="ark-back">
            &larr; Back to Candidate Profile
          </Link>
        }
        title={pkg ? `${pkg.applicant_name} · Pre-Employment Records` : "Pre-Employment Records"}
        description={pkg && `${pkg.job_title} · Accepted ${new Date(pkg.hired_at).toLocaleDateString()}`}
      />

      {loading && <p style={{ fontFamily: "var(--arkive-font)", color: "var(--ink-600)" }}>Loading...</p>}
      {error && <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />}

      {pkg && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* The rest of this package is what the candidate did; this is
              the one card recording what the institution decided about
              it, which is the part a 201 file is actually for. */}
          {pkg.decision && <DecisionRecordPanel decision={pkg.decision} />}

          {/* A hired applicant's permanent record carries the full
              working — the weighting and the agent trail included —
              rather than the summary view HR reads while deciding. */}
          <SynthesisPanel synthesis={pkg.synthesis} expanded />

          <Card padding={16}>
            <SectionLabel>Contact</SectionLabel>
            <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-900)", margin: "8px 0 0" }}>
              {pkg.applicant_name} · {pkg.applicant_email}
            </p>
          </Card>

          {pkg.resume && (
            <Card padding={16}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <DocumentIcon width={16} height={16} />
                  <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-900)", fontWeight: 600 }}>
                    {pkg.resume.original_filename}
                  </span>
                </div>
                <Button
                  variant="secondary"
                  onClick={() => openResumeFile(`/hr/applications/${applicationId}/resume-file`, token)}
                  style={{ padding: "6px 12px", fontSize: "var(--text-sm)" }}
                >
                  <DownloadIcon width={14} height={14} />
                  Download Original
                </Button>
              </div>
              {pkg.resume.skills.length > 0 && (
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 12 }}>
                  {pkg.resume.skills.map((skill) => (
                    <Tag key={skill}>{skill}</Tag>
                  ))}
                </div>
              )}
            </Card>
          )}

          {pkg.letter_of_intent && (
            <Card padding={16}>
              <SectionLabel>Letter of Intent</SectionLabel>
              <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-900)", marginTop: 8, marginBottom: 0, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                {pkg.letter_of_intent}
              </p>
            </Card>
          )}

          {Object.keys(pkg.shortlisting).length > 0 && (
            <Card padding={16}>
              <SectionLabel>Shortlisting</SectionLabel>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
                {Object.entries(pkg.shortlisting).map(([stage, shortlist]) => (
                  <RowLine
                    key={stage}
                    label={shortlist.label}
                    value={
                      shortlist.outcome
                        ? `${capitalize(shortlist.outcome)}${shortlist.notes ? `: ${shortlist.notes}` : ""}`
                        : "Not recorded"
                    }
                  />
                ))}
              </div>
            </Card>
          )}

          {Object.keys(pkg.examinations).length > 0 && (
            <Card padding={16}>
              <SectionLabel>Examinations</SectionLabel>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
                {Object.entries(pkg.examinations).map(([stage, exam]) => (
                  <RowLine key={stage} label={exam.label} value={exam.score != null ? `${exam.score}/100` : "No score recorded"} />
                ))}
              </div>
            </Card>
          )}

          {Object.keys(pkg.interview_ratings).length > 0 && (
            <Card padding={16}>
              <SectionLabel>Interview Rounds</SectionLabel>
              <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 8 }}>
                {Object.entries(pkg.interview_ratings).map(([stage, round]) => (
                  <div key={stage} style={{ paddingBottom: 10, borderBottom: "1px solid var(--surface-border)" }}>
                    <RowLine
                      label={round.label}
                      value={round.computed_score != null ? `${round.computed_score.toFixed(1)} (${round.tier ?? "–"})` : "Not evaluated"}
                    />
                    {round.remarks && (
                      <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", margin: "4px 0 0" }}>
                        &ldquo;{round.remarks}&rdquo;
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}
    </AppShell>
  );
}

function RowLine({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
      <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-900)", fontWeight: 600 }}>{label}</span>
      <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)" }}>{value}</span>
    </div>
  );
}
