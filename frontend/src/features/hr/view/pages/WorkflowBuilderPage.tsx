import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type {
  DashboardSummary,
  EvaluatorAccount,
  RequisitionDetail,
  RequisitionEvaluator,
  WorkflowIssue,
} from "../../../../shared/api/pipeline";
import { AppShell } from "../components/AppShell";
import { JobPickerTable } from "../components/JobPickerTable";
import { WorkflowStagesEditor } from "../components/WorkflowStagesEditor";
import { makeStage, type WorkflowStageDraft } from "../../model/workflowStages";
import { interviewDurations, withInterviewDurations } from "../../model/interviewMinutes";
import { Card } from "../../../../shared/ui/Card";
import { Button } from "../../../../shared/ui/Button";
import { Tag } from "../../../../shared/ui/Tag";
import { Avatar } from "../../../../shared/ui/Avatar";
import { ErrorState } from "../../../../shared/ui/ErrorState";
import { LayersIcon } from "../../../../shared/ui/icons";
import { PageHeader } from "../../../../shared/ui/PageHeader";

/**
 * Two modes, one file:
 *  - No :id in the route ("/hr/workflow-builder") — a picker listing open
 *    jobs with zero active candidates (the only ones whose workflow can be
 *    edited). Draft jobs aren't listed here since /hr/dashboard/summary only
 *    returns open ones — they're reached from the job opening's own page.
 *  - :id present ("/hr/requisitions/:id/workflow") — the real, job-scoped
 *    editor. The ordered stage-type list persists to
 *    JobRequisition.workflow_definition, with the round/exam names and
 *    each interview round's length. The sequence locks once the job has
 *    any active candidate.
 *
 * The stage list itself is WorkflowStagesEditor, shared with Create Job
 * Opening; this page adds loading, saving and the evaluator pool.
 */

export function WorkflowBuilderPage() {
  const { id } = useParams<{ id: string }>();
  return id ? <JobWorkflowEditor requisitionId={Number(id)} /> : <WorkflowJobPicker />;
}

function WorkflowJobPicker() {
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
        title="Workflow Builder"
        info={{
          summary: "Pick an open job to customize its hiring workflow.",
          points: [
            "Once a job has active candidates its stage order is locked.",
            "A locked job still opens, so you can rename its stages and manage its evaluators.",
          ],
        }}
      />

      {loading && <p style={{ fontFamily: "var(--arkive-font)", color: "var(--ink-600)" }}>Loading...</p>}
      {error && <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />}

      {summary && summary.requisitions.length > 0 && (
        <JobPickerTable
          requisitions={summary.requisitions}
          hrefFor={(req) => `/hr/requisitions/${req.id}/workflow`}
          lockedOpens
          subject="workflow"
          lockedHint="Candidates are active, so the stage order is locked. The workflow still opens, and its stage names and evaluator pool stay editable."
        />
      )}

      {summary && summary.requisitions.length === 0 && (
        <Card padding={0}>
          <div className="ark-empty">
            <span className="ark-empty__mark">
              <LayersIcon width={20} height={20} />
            </span>
            <span className="ark-empty__title">No open jobs yet</span>
            <span className="ark-empty__body">
              A workflow belongs to a job opening, so create one first and its hiring process becomes editable here.
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

function JobWorkflowEditor({ requisitionId }: { requisitionId: number }) {
  const { token } = useAuth();
  const [requisition, setRequisition] = useState<RequisitionDetail | null>(null);
  const [stages, setStages] = useState<WorkflowStageDraft[]>([]);
  const [roundLabels, setRoundLabels] = useState<Record<string, string>>({});
  const [examLabels, setExamLabels] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const [pool, setPool] = useState<RequisitionEvaluator[]>([]);
  const [allEvaluators, setAllEvaluators] = useState<EvaluatorAccount[]>([]);
  const [poolError, setPoolError] = useState<string | null>(null);

  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    setLoadError(null);
    apiFetch<RequisitionDetail>(`/hr/requisitions/${requisitionId}`, { token })
      .then((req) => {
        setRequisition(req);
        setStages(withInterviewDurations(req.workflow_definition.map((s) => makeStage(s)), req.interview_durations));
        setRoundLabels(req.interview_round_labels ?? {});
        setExamLabels(req.examination_labels ?? {});
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Failed to load."))
      .finally(() => setLoading(false));
  }, [requisitionId, token, reloadKey]);

  function loadPool() {
    setPoolError(null);
    apiFetch<RequisitionEvaluator[]>(`/hr/requisitions/${requisitionId}/evaluators`, { token })
      .then(setPool)
      .catch((err) => setPoolError(err instanceof ApiError ? err.message : "Failed to load the evaluator pool."));
  }

  useEffect(() => {
    loadPool();
    apiFetch<EvaluatorAccount[]>("/hr/evaluators", { token }).then(setAllEvaluators).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requisitionId, token]);

  const locked = requisition != null && requisition.active_candidate_count > 0;

  // The editor's live checklist, so a save with known errors is held back.
  const [issues, setIssues] = useState<WorkflowIssue[]>([]);
  const hasErrors = issues.some((i) => i.severity === "error");
  const stageKey = stages.map((s) => s.stageType).join(",");

  // What the *database* currently holds, as opposed to the draft on
  // screen -- lets the header flag when the draft and the saved workflow
  // have diverged at all.
  const sequenceDirty = stageKey !== (requisition?.workflow_definition ?? []).join(",");

  async function addToPool(evaluatorId: number) {
    setPoolError(null);
    try {
      await apiFetch(`/hr/requisitions/${requisitionId}/evaluators`, {
        method: "POST",
        token,
        body: { evaluator_id: evaluatorId },
      });
      loadPool();
    } catch (err) {
      setPoolError(err instanceof ApiError ? err.message : "Could not add this evaluator to the pool.");
    }
  }

  async function removeFromPool(evaluatorId: number) {
    setPoolError(null);
    try {
      await apiFetch(`/hr/requisitions/${requisitionId}/evaluators/${evaluatorId}`, {
        method: "DELETE",
        token,
      });
      loadPool();
    } catch (err) {
      setPoolError(err instanceof ApiError ? err.message : "Could not remove this evaluator.");
    }
  }


  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      const updated = await apiFetch<RequisitionDetail>(`/hr/requisitions/${requisitionId}/workflow`, {
        method: "PATCH",
        token,
        body: {
          stages: stages.map((s) => s.stageType),
          interview_round_labels: roundLabels,
          examination_labels: examLabels,
          interview_durations: interviewDurations(stages),
        },
      });
      setRequisition(updated);
      setSaved(true);
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Could not save the workflow.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell>
      <PageHeader
        above={
          <Link to="/hr/workflow-builder" className="ark-back">
            &larr; Choose a different job
          </Link>
        }
        title={requisition ? `${requisition.title} · Hiring Workflow` : "Hiring Workflow"}
        info={{ summary: "Drag stages to reorder, and configure who owns each step." }}
        actions={locked && (
            <Tag tone="amber" dot>
              Stage sequence locked: active candidates
            </Tag>
          )}
      />

      {loading && <p style={{ fontFamily: "var(--arkive-font)", color: "var(--ink-600)" }}>Loading...</p>}
      {loadError && <ErrorState message={loadError} onRetry={() => setReloadKey((k) => k + 1)} />}

      {requisition && (
        <>
          <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", maxWidth: 640, marginTop: 0, marginBottom: 24 }}>
            {locked
              ? "This job has active candidates, so the stage sequence is fixed. Reordering or removing a stage now could invalidate where those candidates currently stand. Everything else here is still editable: renaming a round or an examination, an interview's length, and the evaluator pool. The sequence unlocks once nobody is active in this pipeline (e.g. once everyone's hired or rejected)."
              : "Set the stages in the order candidates go through them, name each interview round and examination, and choose how long each interview runs."}
          </p>

          <WorkflowStagesEditor
            stages={stages}
            onStagesChange={setStages}
            roundLabels={roundLabels}
            onRoundLabelsChange={setRoundLabels}
            examLabels={examLabels}
            onExamLabelsChange={setExamLabels}
            locked={locked}
            onIssuesChange={setIssues}
            footer={
              <>
                {/* "Unsaved changes" wins over a stale "Saved." — editing after
                    a save must not keep claiming the draft is stored, since
                    that is the whole confusion the exam-slot trap grew out of. */}
                {sequenceDirty ? (
                  <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--warning-text)", fontWeight: 600 }}>
                    Unsaved changes
                  </span>
                ) : (
                  saved && <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--success-text)" }}>Saved.</span>
                )}
                {/* Disabled on a known error (the checklist above says why), so
                    the broken save is stopped before it is attempted. The
                    server still validates regardless — this is the courtesy,
                    the 422 is the guarantee. Not disabled while locked, where
                    only labels are being saved and the sequence is untouched. */}
                <Button
                  variant="primary"
                  onClick={handleSave}
                  disabled={saving || stages.length === 0 || (!locked && hasErrors)}
                  title={!locked && hasErrors ? "Fix the errors above before saving" : undefined}
                >
                  {saving ? "Saving..." : locked ? "Save Names & Lengths" : "Save Workflow"}
                </Button>
              </>
            }
          />
          {saveError && <p style={{ color: "crimson", marginTop: 12 }}>{saveError}</p>}

          {/* No "View Pipeline Instead" escape hatch here any more: a locked
              job is meant to stay on its workflow page (the sequence is just
              read-only), not be nudged off to the pipeline — that divergence
              was the reported bug. The nav still reaches the pipeline. */}

          <h2 style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xl)", fontWeight: 700, color: "var(--ink-900)", marginTop: 40, maxWidth: 860 }}>
            Evaluator Pool
          </h2>
          <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", maxWidth: 640, marginTop: 4, marginBottom: 16 }}>
            Evaluators eligible to conduct this job's interview rounds. Assign a specific pool member to a specific
            candidate's round from their Candidate Profile page. Not locked by active candidates: adding or removing
            pool members doesn't touch any in-flight interview assignment.
          </p>

          <Card padding={16} elevation="md" style={{ maxWidth: 860 }}>
            {pool.length === 0 && (
              <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", margin: 0 }}>
                No evaluators in this job's pool yet.
              </p>
            )}
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {pool.map((member) => (
                <div key={member.id} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <Avatar name={member.full_name} size={28} src={member.avatar_url} />
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ display: "block", fontFamily: "var(--arkive-font)", fontWeight: 600, fontSize: "var(--text-base)", color: "var(--ink-900)" }}>
                      {member.full_name}
                    </span>
                    {/* Their own title and office, from Account Settings —
                        so HR can tell who is who by role, not only by name. */}
                    {(member.job_title || member.department) && (
                      <span style={{ display: "block", fontFamily: "var(--arkive-font)", fontSize: "var(--text-xs)", color: "var(--ink-700)", marginTop: 1 }}>
                        {[member.job_title, member.department].filter(Boolean).join(" · ")}
                      </span>
                    )}
                  </span>
                  <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)" }}>{member.email}</span>
                  {/* Switched off after joining the pool: they stay (their
                      history on this job stays), but can't take a new
                      interview — the Interviews tab won't offer them. */}
                  {!member.is_active && (
                    <Tag tone="amber" dot title="This evaluator's account is deactivated, so they can't be given new interviews.">
                      Deactivated
                    </Tag>
                  )}
                  {/* No remove control once they've conducted an interview
                      for this job (HR feedback): someone with real history on
                      the job shouldn't be dropped on a stray click. A small
                      "Conducted" tag takes the "×"'s place so the row still
                      reads as intentional, not broken. */}
                  {member.has_conducted ? (
                    <span
                      title="This evaluator has submitted a scorecard for this job and can no longer be removed from the pool."
                      style={{
                        fontFamily: "var(--arkive-font)",
                        fontSize: "var(--text-xs)",
                        fontWeight: 600,
                        color: "var(--success-text)",
                        padding: "2px 8px",
                        borderRadius: 999,
                        background: "var(--success-bg)",
                      }}
                    >
                      Conducted
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => removeFromPool(member.evaluator_id)}
                      aria-label="Remove from pool"
                      style={{ border: "none", background: "transparent", color: "var(--ink-400)", fontSize: "var(--text-xl)", lineHeight: 1, cursor: "pointer", padding: 4 }}
                    >
                      &times;
                    </button>
                  )}
                </div>
              ))}
            </div>

            {(() => {
              const poolIds = new Set(pool.map((m) => m.evaluator_id));
              const available = allEvaluators.filter((e) => !poolIds.has(e.id));
              if (available.length === 0) return null;
              return (
                <select
                  defaultValue=""
                  onChange={(e) => {
                    if (e.target.value) addToPool(Number(e.target.value));
                    e.target.value = "";
                  }}
                  style={{ ...fieldStyle, marginTop: pool.length > 0 ? 12 : 0, width: 260 }}
                >
                  <option value="" disabled>
                    + Add evaluator to pool...
                  </option>
                  {available.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.full_name} ({e.email})
                    </option>
                  ))}
                </select>
              );
            })()}
            {poolError && <ErrorState message={poolError} onRetry={loadPool} />}
          </Card>

        </>
      )}
    </AppShell>
  );
}

const fieldStyle: React.CSSProperties = {
  padding: "8px 10px",
  borderRadius: "var(--radius)",
  border: "1px solid var(--surface-border)",
  fontSize: "var(--text-sm)",
  fontFamily: "var(--arkive-font)",
  color: "var(--ink-900)",
  background: "var(--surface)",
  boxSizing: "border-box",
};
