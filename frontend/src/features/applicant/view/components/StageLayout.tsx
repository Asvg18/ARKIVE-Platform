import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { apiFetch, ApiError, openFile } from "../../../../shared/api/client";
import type { ApplicationDetail } from "../../../../shared/api/applicant";
import { openResumeFile } from "../../../../shared/api/resume";
import { APPLICANT_STATUS_LABELS } from "../../../../shared/lib/stageLabels";
import { applicationStatusTone } from "../../../../shared/lib/statusTags";
import { identityColor, initials } from "../../../../shared/lib/identity";
import { ApplicantAppShell } from "./ApplicantAppShell";
import { ApplicationJourney } from "./ApplicationJourney";
import { Card } from "../../../../shared/ui/Card";
import { Button } from "../../../../shared/ui/Button";
import { IdentityMark } from "../../../../shared/ui/IdentityMark";
import { ConfirmDialog } from "../../../../shared/ui/ConfirmDialog";
import { DocumentIcon, PlusIcon, UploadIcon } from "../../../../shared/ui/icons";

/** Shared per-stage layout -- a page header, then the stage's own screen
 * with a rail of the journey and documents beside it, reused by every
 * per-stage screen so each one
 * only renders its own inner content, not its own page chrome.
 * Deliberately no "Application Support" recruiter contact card -- no
 * assigned-recruiter data model, and inventing a named contact with a
 * fake photo isn't consistent with this project's rule against
 * fabricating data that looks real.
 *
 * Also no Skill Match sidebar card -- Skill Matching's score/strengths/
 * gaps/summary are HR-only (showing a candidate a critical AI analysis
 * of their own shortcomings is discouraging even when it's a pass); the
 * backend never sends those fields to the applicant anyway.
 *
 * DOES have an Exam Result card -- a numeric score/percentile is a
 * plain fact, not a subjective critique, so it's shown once HR records
 * it. Lives here rather than in ScheduleScreen because it needs to stay
 * visible after the exam stage advances past.
 *
 * Also owns "Cancel Application" (a header action, confirmed via
 * ConfirmDialog) and "Add More Documents" (inline upload form on the
 * documents card) -- both live here rather than in a per-stage screen
 * since they're properties of the *application*, not whichever stage
 * happens to be active. */
export function StageLayout({
  application,
  onUpdate,
  children,
}: {
  application: ApplicationDetail;
  onUpdate: (updated: ApplicationDetail) => void;
  children: ReactNode;
}) {
  const { token } = useAuth();
  const resumeFilename = application.resume?.original_filename ?? null;
  const isActive = application.status === "active";

  const statusTone = applicationStatusTone(application.status);

  return (
    // Wide, in two columns: the stage's own screen — the thing to do —
    // leads on the left, and the journey and documents sit in a rail
    // beside it, so the task is never pushed below the fold by the list
    // of stages.
    <ApplicantAppShell wide>
      <div style={{ marginBottom: 12 }}>
        <Link to="/applicant" className="ark-back">
          &larr; My Applications
        </Link>
      </div>

      <ApplicationHero application={application} statusTone={statusTone} />

      <div className="ark-stage-layout">
        <div className="ark-stage-layout__main">
          <Card padding={28}>{children}</Card>

          {/* withdrawing is the only irreversible thing an applicant can
              do here, and used to sit in the header's top-right slot --
              the position a page's *primary* action occupies, one
              mis-click from ending an application. reads as what it is
              down here, after everything it would undo. */}
          {isActive && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 16,
                flexWrap: "wrap",
                padding: "14px 16px",
                borderRadius: "var(--radius)",
                border: "1px solid var(--surface-border)",
              }}
            >
              <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", margin: 0 }}>
                No longer interested in this position?
              </p>
              <WithdrawAction application={application} token={token} onUpdate={onUpdate} />
            </div>
          )}
        </div>

        <aside className="ark-stage-layout__rail" aria-label="Application progress and documents">
          <Card padding={20}>
            {/* The current stage's own screen is beside this, so the
                journey drops its "Continue" button (it would link to this
                page) and its appointment line (that screen states the
                date, time and meeting link in full). */}
            <ApplicationJourney application={application} stageScreenBelow />
          </Card>

          <Card padding={20}>
            <div style={sectionLabel}>Associated Documents</div>
            {resumeFilename ? (
              <button
                type="button"
                onClick={() => openResumeFile(`/applicant/applications/${application.id}/resume-file`, token)}
                style={documentLinkButton}
              >
                <DocumentIcon width={16} height={16} style={{ color: "var(--accent)", flexShrink: 0 }} />
                <span style={documentLinkText}>{resumeFilename}</span>
              </button>
            ) : (
              <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-400)", fontStyle: "italic", marginTop: 12 }}>
                No documents uploaded yet.
              </p>
            )}

            {application.documents.length > 0 && (
              <div style={{ marginTop: resumeFilename ? 10 : 12, display: "flex", flexDirection: "column", gap: 10 }}>
                {application.documents.map((doc) => (
                  <button
                    key={doc.id}
                    type="button"
                    onClick={() =>
                      openFile(
                        `/applicant/applications/${application.id}/documents/${doc.id}/file`,
                        token,
                        "Could not download this document."
                      )
                    }
                    style={documentLinkButton}
                  >
                    <DocumentIcon width={16} height={16} style={{ color: "var(--accent)", flexShrink: 0 }} />
                    <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", minWidth: 0 }}>
                      <span style={{ ...documentLinkText, fontWeight: 600 }}>{doc.label}</span>
                      <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-2xs)", color: "var(--ink-400)", textDecoration: "none" }}>
                        {doc.original_filename}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            )}

            {isActive && <AddDocumentForm application={application} token={token} onUpdate={onUpdate} />}
          </Card>

          {Object.keys(application.examination_results).length > 0 && (
            <Card padding={20}>
              <div style={sectionLabel}>Exam Result</div>
              {Object.values(application.examination_results).map((result) => (
                <div key={result.label} style={{ marginTop: 12 }}>
                  <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", margin: 0 }}>
                    {result.label}
                  </p>
                  <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xl)", fontWeight: 700, color: "var(--ink-900)", margin: "2px 0 0" }}>
                    {result.score}
                  </p>
                </div>
              ))}
              {application.exam_percentile !== null && (
                <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", marginTop: 12, lineHeight: 1.5 }}>
                  You scored better than {application.exam_percentile}% of other applicants for this role.
                </p>
              )}
            </Card>
          )}
        </aside>
      </div>
    </ApplicantAppShell>
  );
}

/** The banner at the head of the page: the job, its department, and in
 * one line where the application stands — the current stage by name, or
 * the outcome once it has closed. The rail beside the stage screen has
 * the full journey; this is the sentence version of it. */
function ApplicationHero({ application, statusTone }: { application: ApplicationDetail; statusTone: string }) {
  const stages = application.stage_instances;
  const closed = application.status !== "active" && application.status !== "flagged";
  const currentIndex = closed ? -1 : stages.findIndex((s) => s.status === "in_progress");
  const current = currentIndex >= 0 ? stages[currentIndex] : null;
  const statusLabel = APPLICANT_STATUS_LABELS[application.status] ?? application.status;

  return (
    <section className="ark-app-hero" aria-labelledby="app-hero-title">
      <IdentityMark initials={initials(application.job_department)} color={identityColor(application.job_department)} size="xl" />

      <div className="ark-app-hero__text">
        <span className="ark-app-hero__eyebrow">Your application</span>
        <h1 id="app-hero-title" className="ark-app-hero__title">
          {application.job_title}
        </h1>
        <div className="ark-app-hero__meta">
          <span>{application.job_department}</span>
          <span className="ark-app-hero__sep" aria-hidden="true" />
          {current ? (
            <span>
              Stage {currentIndex + 1} of {stages.length} · <strong>{current.label}</strong>
            </span>
          ) : (
            <span>
              {stages.filter((s) => s.status === "complete").length} of {stages.length} stages complete
            </span>
          )}
        </div>
      </div>

      <span className="ark-app-hero__status" data-tone={statusTone}>
        {statusLabel}
      </span>
    </section>
  );
}

function WithdrawAction({
  application,
  token,
  onUpdate,
}: {
  application: ApplicationDetail;
  token: string | null;
  onUpdate: (updated: ApplicationDetail) => void;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [withdrawing, setWithdrawing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConfirm() {
    setWithdrawing(true);
    setError(null);
    try {
      const updated = await apiFetch<ApplicationDetail>(`/applicant/applications/${application.id}/withdraw`, {
        method: "POST",
        token,
      });
      onUpdate(updated);
      setConfirmOpen(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not withdraw this application.");
    } finally {
      setWithdrawing(false);
    }
  }

  return (
    <>
      <Button
        variant="outline"
        onClick={() => {
          setError(null);
          setConfirmOpen(true);
        }}
        style={{ fontSize: "var(--text-sm)", padding: "8px 14px", color: "var(--warning-text)", borderColor: "var(--warning-text)" }}
      >
        Cancel Application
      </Button>
      <ConfirmDialog
        open={confirmOpen}
        title="Cancel this application?"
        description={`This withdraws your application for ${application.job_title}. HR will see it as withdrawn, and you won't be able to continue this application afterward. This can't be undone by you. You'd need to reapply.`}
        confirmLabel="Cancel Application"
        cancelLabel="Keep Application"
        confirming={withdrawing}
        onConfirm={handleConfirm}
        onCancel={() => setConfirmOpen(false)}
      />
      {error && (
        <div
          role="alert"
          style={{ position: "fixed", bottom: 24, right: 24, zIndex: 100, background: "var(--warning-bg)", color: "var(--warning-text)", padding: "10px 16px", borderRadius: "var(--radius)", fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", fontWeight: 600, boxShadow: "0 12px 28px rgba(15, 23, 42, 0.14)" }}
        >
          {error}
        </div>
      )}
    </>
  );
}

function AddDocumentForm({
  application,
  token,
  onUpdate,
}: {
  application: ApplicationDetail;
  token: string | null;
  onUpdate: (updated: ApplicationDetail) => void;
}) {
  const [open, setOpen] = useState(false);
  const [label, setLabel] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    if (!file || !label.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("label", label.trim());
      const updated = await apiFetch<ApplicationDetail>(`/applicant/applications/${application.id}/documents`, {
        method: "POST",
        token,
        body: formData,
      });
      onUpdate(updated);
      setLabel("");
      setFile(null);
      setOpen(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add this document.");
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          marginTop: 14,
          background: "none",
          border: "none",
          padding: 0,
          cursor: "pointer",
        }}
      >
        <PlusIcon width={14} height={14} style={{ color: "var(--ink-600)" }} />
        <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--ink-600)" }}>
          Add More Documents
        </span>
      </button>
    );
  }

  return (
    <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--surface-border)" }}>
      <label style={{ display: "block", fontFamily: "var(--arkive-font)", fontSize: "var(--text-2xs)", fontWeight: 700, color: "var(--ink-600)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
        Document Name
      </label>
      <input
        type="text"
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        placeholder="e.g. Reference Letter"
        style={{
          display: "block",
          width: "100%",
          padding: "8px 10px",
          borderRadius: "var(--radius)",
          border: "1px solid var(--surface-border)",
          background: "var(--surface)",
          fontFamily: "var(--arkive-font)",
          fontSize: "var(--text-sm)",
          color: "var(--ink-900)",
          boxSizing: "border-box",
        }}
      />

      <label
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginTop: 10,
          border: "1.5px dashed var(--surface-border)",
          borderRadius: "var(--radius)",
          padding: "10px 12px",
          background: "var(--surface-bg)",
          cursor: "pointer",
        }}
      >
        <UploadIcon width={14} height={14} style={{ color: "var(--accent)", flexShrink: 0 }} />
        <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: file ? "var(--ink-900)" : "var(--ink-400)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {file ? file.name : "Choose a PDF"}
        </span>
        <input
          type="file"
          accept=".pdf,application/pdf"
          onChange={(e) => e.target.files?.[0] && setFile(e.target.files[0])}
          style={{ display: "none" }}
        />
      </label>

      {error && <p style={{ color: "crimson", fontSize: "var(--text-xs)", marginTop: 8, marginBottom: 0 }}>{error}</p>}

      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <Button
          variant="ghost"
          disabled={submitting}
          onClick={() => {
            setOpen(false);
            setLabel("");
            setFile(null);
            setError(null);
          }}
          style={{ fontSize: "var(--text-sm)", padding: "6px 4px" }}
        >
          Cancel
        </Button>
        <Button
          variant="secondary"
          disabled={submitting || !file || !label.trim()}
          onClick={handleSubmit}
          style={{ fontSize: "var(--text-sm)", padding: "6px 14px" }}
        >
          {submitting ? "Uploading..." : "Upload"}
        </Button>
      </div>
    </div>
  );
}

const sectionLabel: React.CSSProperties = {
  fontFamily: "var(--arkive-font)",
  fontSize: "var(--text-xs)",
  fontWeight: 700,
  color: "var(--ink-600)",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};

const documentLinkButton: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  marginTop: 12,
  background: "none",
  border: "none",
  padding: 0,
  cursor: "pointer",
  textAlign: "left",
  width: "100%",
};

const documentLinkText: React.CSSProperties = {
  fontFamily: "var(--arkive-font)",
  fontSize: "var(--text-sm)",
  color: "var(--accent)",
  textDecoration: "underline",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};
