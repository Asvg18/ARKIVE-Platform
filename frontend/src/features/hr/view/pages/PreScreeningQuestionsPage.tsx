import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { DashboardSummary, PreScreeningQuestion, RequisitionDetail } from "../../../../shared/api/pipeline";
import { AppShell } from "../components/AppShell";
import { JobPickerTable } from "../components/JobPickerTable";
import { PreScreeningQuestionsEditor } from "../components/PreScreeningQuestionsEditor";
import { Card } from "../../../../shared/ui/Card";
import { Button } from "../../../../shared/ui/Button";
import { Tag } from "../../../../shared/ui/Tag";
import { ErrorState } from "../../../../shared/ui/ErrorState";
import { DocumentIcon } from "../../../../shared/ui/icons";
import { PageHeader } from "../../../../shared/ui/PageHeader";

/**
 * HR-editable AI Pre-Screening question set per job. Two modes, as in
 * WorkflowBuilderPage.tsx: a picker ("/hr/pre-screening-questions") and a
 * job-scoped editor ("/hr/requisitions/:id/pre-screening-questions").
 * The question list itself is PreScreeningQuestionsEditor, shared with
 * Create Job Opening.
 *
 * The required exam-availability step(s) applicants also answer during
 * pre-screening are NOT edited here — they're auto-derived from the
 * job's workflow (one per examination_k stage) and always required, not
 * HR-authored content.
 */

export function PreScreeningQuestionsPage() {
  const { id } = useParams<{ id: string }>();
  return id ? <JobQuestionsEditor requisitionId={Number(id)} /> : <QuestionsJobPicker />;
}

function QuestionsJobPicker() {
  const { token } = useAuth();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    setError(null);
    apiFetch<DashboardSummary>("/hr/dashboard/summary", { token })
      .then(setSummary)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load."))
      .finally(() => setLoading(false));
  }, [token, reloadKey]);

  return (
    <AppShell>
      <PageHeader
        title="Pre-Screening Questions"
        info={{
          summary: "Pick an open job to customize the questions its applicants are asked during Pre-Screening.",
          points: ["Questions lock while a job has active candidates, so everyone in a pipeline answers the same set."],
        }}
      />

      {loading && <p style={{ fontFamily: "var(--arkive-font)", color: "var(--ink-600)" }}>Loading...</p>}
      {error && <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />}

      {/* The same table as the Workflow Builder's picker, and deliberately
          so: both screens choose a job opening and then configure one
          thing about it. The difference is that a locked job here does
          not open at all — its questions genuinely cannot change, and a
          row that looks clickable and then refuses is worse than one that
          never offered. */}
      {summary && summary.requisitions.length > 0 && (
        <JobPickerTable
          requisitions={summary.requisitions}
          hrefFor={(req) => `/hr/requisitions/${req.id}/pre-screening-questions`}
          lockedOpens={false}
          subject="pre-screening questions"
          lockedHint="Candidates are active, so the questions are fixed and every candidate answers the same set. Editing reopens once nobody is active in this pipeline."
        />
      )}

      {summary && summary.requisitions.length === 0 && (
        <Card padding={0}>
          <div className="ark-empty">
            <span className="ark-empty__mark">
              <DocumentIcon width={20} height={20} />
            </span>
            <span className="ark-empty__title">No open jobs yet</span>
            <span className="ark-empty__body">
              Pre-screening questions belong to a job opening, so create one first and its questions become editable here.
            </span>
            <Link to="/hr/requisitions/new" style={{ textDecoration: "none", marginTop: 4 }}>
              <Button variant="secondary" size="sm">Create Job Opening</Button>
            </Link>
          </div>
        </Card>
      )}
    </AppShell>
  );
}

function JobQuestionsEditor({ requisitionId }: { requisitionId: number }) {
  const { token } = useAuth();
  const [requisition, setRequisition] = useState<RequisitionDetail | null>(null);
  const [questions, setQuestions] = useState<PreScreeningQuestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    setLoadError(null);
    apiFetch<RequisitionDetail>(`/hr/requisitions/${requisitionId}`, { token })
      .then((req) => {
        setRequisition(req);
        setQuestions(req.pre_screening_questions);
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Failed to load."))
      .finally(() => setLoading(false));
  }, [requisitionId, token, reloadKey]);

  const locked = requisition != null && requisition.active_candidate_count > 0;

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      const updated = await apiFetch<RequisitionDetail>(
        `/hr/requisitions/${requisitionId}/pre-screening-questions`,
        { method: "PATCH", token, body: { questions } }
      );
      setRequisition(updated);
      setQuestions(updated.pre_screening_questions);
      setSaved(true);
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Could not save the questions.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell>
      <PageHeader
        above={
          <Link to="/hr/pre-screening-questions" className="ark-back">
            &larr; Choose a different job
          </Link>
        }
        title={requisition ? `${requisition.title} · Pre-Screening Questions` : "Pre-Screening Questions"}
        info={{
          summary: "The questions this job's applicants answer during Pre-Screening, asked in the order shown here.",
          points: [
            "Applicants also answer a required exam-availability step for each examination stage in this job's workflow.",
            "That step comes from the job's workflow, so it is set in the Workflow Builder, not here.",
          ],
        }}
        actions={locked && (
            <Tag tone="amber" dot>
              Locked: active candidates in this pipeline
            </Tag>
          )}
      />

      {loading && <p style={{ fontFamily: "var(--arkive-font)", color: "var(--ink-600)" }}>Loading...</p>}
      {loadError && <ErrorState message={loadError} onRetry={() => setReloadKey((k) => k + 1)} />}

      {requisition && (
        <>
          {locked && (
            <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", maxWidth: 640, marginTop: 0, marginBottom: 24 }}>
              This job already has active candidates. Editing or removing a question now could orphan their
              already-submitted answers, so editing is locked. It'll reopen once nobody's active in this pipeline.
            </p>
          )}

          <div style={{ marginTop: 24 }}>
            <PreScreeningQuestionsEditor
              questions={questions}
              onChange={setQuestions}
              locked={locked}
              footer={
                !locked && (
                  <>
                    {saved && <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--success-text)" }}>Saved.</span>}
                    <Button variant="primary" onClick={handleSave} disabled={saving}>
                      {saving ? "Saving..." : "Save Questions"}
                    </Button>
                  </>
                )
              }
            />
          </div>
          {saveError && <p style={{ color: "crimson", marginTop: 12 }}>{saveError}</p>}
        </>
      )}
    </AppShell>
  );
}
