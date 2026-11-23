import { useEffect, useState, type DragEvent, type Dispatch, type ReactNode, type SetStateAction } from "react";
import { useAuth } from "../../../auth/controller/AuthContext";
import { apiFetch } from "../../../../shared/api/client";
import type { WorkflowIssue, WorkflowValidationResponse } from "../../../../shared/api/pipeline";
import { Card } from "../../../../shared/ui/Card";
import { Button } from "../../../../shared/ui/Button";
import { isExamStage, isInterviewStage, stageLabel } from "../../../../shared/lib/stageLabels";
import { INTERVIEW_MINUTES, interviewMinutes } from "../../model/interviewMinutes";
import { makeStage, type WorkflowStageDraft } from "../../model/workflowStages";

/**
 * A job's stage list, edited: drag to reorder, name the interview rounds
 * and examinations, add or remove the optional stages — with the
 * server's live checklist underneath. Shared by the Workflow Builder
 * (an existing job) and Create Job Opening (a job not yet saved), so
 * both edit a workflow the same way.
 *
 * It holds no job and saves nothing: the page owns the stages and labels
 * and decides what saving means. `footer` sits at the right end of the
 * add-buttons row for the page's own save/continue controls.
 */

/** Stages every workflow keeps (app.domain.workflow_rules): Document
 *  Upload is where an application begins, Shortlisting comes before the
 *  interviews, and the hire is recorded at Final Decision and handed to
 *  Onboarding. They get no remove button; the server refuses a workflow
 *  without any of them. Since they can't be removed they can't be added
 *  either, and a row's stage can't be switched to another:
 *  the only stages HR adds are Pre-Screening, interview rounds and
 *  examinations, each through its own button. The server also requires
 *  at least one interview round. */
const REQUIRED_STAGES = new Set(["document_upload", "shortlisting", "final_decision", "onboarding"]);

const PRE_SCREENING = "skill_matching";

const MAX_INTERVIEW_ROUNDS = 6;
const MAX_EXAMINATIONS = 4;

export function WorkflowStagesEditor({
  stages,
  onStagesChange,
  roundLabels,
  onRoundLabelsChange,
  examLabels,
  onExamLabelsChange,
  locked = false,
  onIssuesChange,
  footer,
}: {
  stages: WorkflowStageDraft[];
  onStagesChange: Dispatch<SetStateAction<WorkflowStageDraft[]>>;
  roundLabels: Record<string, string>;
  onRoundLabelsChange: Dispatch<SetStateAction<Record<string, string>>>;
  examLabels: Record<string, string>;
  onExamLabelsChange: Dispatch<SetStateAction<Record<string, string>>>;
  /** The sequence is fixed (a job with active candidates); names stay editable. */
  locked?: boolean;
  /** The live checklist's result, so the page can hold back a save. */
  onIssuesChange?: (issues: WorkflowIssue[]) => void;
  footer?: ReactNode;
}) {
  const { token } = useAuth();
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);

  // The live checklist. `stageKey` is the ordered stage list as a plain
  // string, so the validation effect re-runs when the *sequence* changes
  // and not when a label or an interview's length does — those can't make a workflow
  // more or less sensible.
  const [issues, setIssues] = useState<WorkflowIssue[]>([]);
  const stageKey = stages.map((s) => s.stageType).join(",");

  function report(next: WorkflowIssue[]) {
    setIssues(next);
    onIssuesChange?.(next);
  }

  // Ask the server — the one authority (app.domain.workflow_rules) —
  // whether the current draft is sensible, debounced so a drag-reorder
  // doesn't fire a request per intermediate frame. Deliberately not a
  // client-side re-derivation of the rules: a second copy of "what makes
  // a workflow valid" is exactly the kind of thing that drifts from the
  // copy the save enforces, so the checklist shows precisely what the
  // save will decide. Skipped while locked — the sequence can't change
  // then, so there is nothing for a checklist to guide.
  useEffect(() => {
    if (locked || stages.length === 0) {
      report([]);
      return;
    }
    const handle = window.setTimeout(() => {
      apiFetch<WorkflowValidationResponse>("/hr/requisitions/validate-workflow", {
        method: "POST",
        token,
        body: { stages: stages.map((s) => s.stageType) },
      })
        .then((res) => report(res.issues))
        .catch(() => {
          // A failed check is not a reason to block editing — the save is
          // still validated server-side, so the checklist just goes quiet.
          report([]);
        });
    }, 300);
    return () => window.clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stageKey, locked, token]);

  function updateStage(stageId: string, patch: Partial<WorkflowStageDraft>) {
    onStagesChange((prev) => prev.map((s) => (s.id === stageId ? { ...s, ...patch } : s)));
  }

  function removeStage(stageId: string) {
    onStagesChange((prev) => prev.filter((s) => s.id !== stageId));
  }

  const hasPreScreening = stages.some((s) => s.stageType === PRE_SCREENING);

  /** Pre-Screening goes straight after Document Upload, the one place the
   *  server allows it. */
  function addPreScreening() {
    if (hasPreScreening) return;
    onStagesChange((prev) => {
      const next = [...prev];
      next.splice(prev.findIndex((s) => s.stageType === "document_upload") + 1, 0, makeStage(PRE_SCREENING));
      return next;
    });
  }

  const usedInterviewRounds = new Set(stages.map((s) => s.stageType).filter(isInterviewStage));
  const nextInterviewRound = Array.from({ length: MAX_INTERVIEW_ROUNDS }, (_, i) => `interview_round_${i + 1}`).find(
    (slot) => !usedInterviewRounds.has(slot)
  );

  function addInterviewRound() {
    if (!nextInterviewRound) return;
    onStagesChange((prev) => [...prev, makeStage(nextInterviewRound)]);
    onRoundLabelsChange((prev) => ({ ...prev, [nextInterviewRound]: prev[nextInterviewRound] ?? "" }));
  }

  const usedExaminations = new Set(stages.map((s) => s.stageType).filter(isExamStage));
  const nextExamination = Array.from({ length: MAX_EXAMINATIONS }, (_, i) => `examination_${i + 1}`).find(
    (slot) => !usedExaminations.has(slot)
  );

  function addExamination() {
    if (!nextExamination) return;
    onStagesChange((prev) => [...prev, makeStage(nextExamination)]);
    onExamLabelsChange((prev) => ({ ...prev, [nextExamination]: prev[nextExamination] ?? stageLabel(nextExamination) }));
  }

  function handleDragStart(index: number) {
    setDraggedIndex(index);
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>, index: number) {
    e.preventDefault();
    if (draggedIndex === null || draggedIndex === index) return;
    onStagesChange((prev) => {
      const next = [...prev];
      const [moved] = next.splice(draggedIndex, 1);
      next.splice(index, 0, moved);
      return next;
    });
    setDraggedIndex(index);
  }

  function handleDragEnd() {
    setDraggedIndex(null);
  }

  return (
    <>
      <Card padding={0} elevation="md" style={{ maxWidth: 860 }}>
        <div style={{ display: "flex", flexDirection: "column" }}>
          {stages.map((stage, index) => (
            // One grid for every row (.ark-stage-row), so the name, length
            // and remove columns line up down the list whichever field a
            // row holds, whether it has a length (interview rounds only)
            // and whether or not its stage can be removed.
            <div
              key={stage.id}
              className="ark-stage-row"
              data-locked={locked || undefined}
              data-dragging={draggedIndex === index || undefined}
              draggable={!locked}
              onDragStart={() => handleDragStart(index)}
              onDragOver={(e) => handleDragOver(e, index)}
              onDragEnd={handleDragEnd}
            >
              {!locked && (
                <span aria-hidden className="ark-stage-row__drag" title="Drag to reorder">
                  ⋮⋮
                </span>
              )}

              <span className="ark-stage-row__num">{index + 1}</span>

              {/* Round and examination names stay editable while the
                  sequence is locked — they are display-only labels, so a
                  rename cannot move anyone's DFA position, and a job
                  shouldn't be uncorrectable for as long as it has
                  candidates in it. The backend agrees: a save that leaves
                  the stage list untouched is allowed regardless. */}
              {isInterviewStage(stage.stageType) ? (
                <input
                  className="ark-input ark-stage-row__name"
                  value={roundLabels[stage.stageType] ?? ""}
                  onChange={(e) => onRoundLabelsChange((prev) => ({ ...prev, [stage.stageType]: e.target.value }))}
                  placeholder={`e.g. ${stageLabel(stage.stageType)}`}
                  aria-label="Interview round name"
                />
              ) : isExamStage(stage.stageType) ? (
                // Prefilled with the exam's default name ("Examination",
                // "Examination 2", ...) rather than an empty box with a
                // placeholder -- still editable.
                <input
                  className="ark-input ark-stage-row__name"
                  value={examLabels[stage.stageType] ?? stageLabel(stage.stageType)}
                  onChange={(e) => onExamLabelsChange((prev) => ({ ...prev, [stage.stageType]: e.target.value }))}
                  placeholder={`e.g. ${stageLabel(stage.stageType)}`}
                  aria-label="Examination name"
                />
              ) : (
                <span className="ark-stage-row__name">{stageLabel(stage.stageType)}</span>
              )}

              {isInterviewStage(stage.stageType) ? (
                <select
                  className="ark-input ark-stage-row__length"
                  value={interviewMinutes(stage)}
                  onChange={(e) => updateStage(stage.id, { minutes: Number(e.target.value) })}
                  aria-label="Interview length"
                  title="Saved with the job: the evaluator's free time is cut into slots this long."
                >
                  {INTERVIEW_MINUTES.map((minutes) => (
                    <option key={minutes} value={minutes}>
                      {minutes} min
                    </option>
                  ))}
                </select>
              ) : (
                <span className="ark-stage-row__length" aria-hidden="true" />
              )}

              {/* A required stage can't be removed; its cell stays,
                  empty, so the row keeps the same columns. */}
              {!locked &&
                (!REQUIRED_STAGES.has(stage.stageType) ? (
                  <button
                    type="button"
                    className="ark-stage-row__remove"
                    onClick={() => removeStage(stage.id)}
                    aria-label="Remove stage"
                  >
                    &times;
                  </button>
                ) : (
                  <span className="ark-stage-row__remove" aria-hidden="true" />
                ))}
            </div>
          ))}

          {stages.length === 0 && (
            <div style={{ padding: 24, textAlign: "center", color: "var(--ink-600)", fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)" }}>
              No stages. Add one below.
            </div>
          )}
        </div>
      </Card>

      {!locked && issues.length > 0 && (
        <div style={{ maxWidth: 860, marginTop: 16, display: "flex", flexDirection: "column", gap: 8 }}>
          {issues.map((issue) => {
            const isError = issue.severity === "error";
            return (
              <div
                key={`${issue.code}-${issue.message}`}
                role={isError ? "alert" : undefined}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 10,
                  padding: "10px 14px",
                  borderRadius: "var(--radius)",
                  background: isError ? "var(--accent-bg)" : "var(--warning-bg)",
                  border: `1px solid ${isError ? "var(--accent)" : "var(--warning-text)"}`,
                }}
              >
                <span style={{ fontSize: "var(--text-base)", lineHeight: 1.5, flexShrink: 0, color: isError ? "var(--accent)" : "var(--warning-text)" }}>
                  {isError ? "✕" : "!"}
                </span>
                <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", lineHeight: 1.5, color: "var(--ink-900)" }}>
                  {issue.message}
                </span>
              </div>
            );
          })}
        </div>
      )}
      {!locked && issues.length === 0 && stages.length > 0 && (
        <div style={{ maxWidth: 860, marginTop: 16 }}>
          <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--success-text)", fontWeight: 600 }}>
            ✓ This workflow is well-formed.
          </span>
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 16, maxWidth: 860, flexWrap: "wrap" }}>
        {!locked && (
          <>
            <Button
              variant="outline"
              onClick={addPreScreening}
              disabled={hasPreScreening}
              title={hasPreScreening ? "This workflow already has Pre-Screening" : undefined}
            >
              + Add Pre-Screening
            </Button>
            <Button
              variant="outline"
              onClick={addInterviewRound}
              disabled={!nextInterviewRound}
              title={nextInterviewRound ? undefined : `All ${MAX_INTERVIEW_ROUNDS} interview rounds are already in use`}
            >
              + Add Interview Round
            </Button>
            <Button
              variant="outline"
              onClick={addExamination}
              disabled={!nextExamination}
              title={nextExamination ? undefined : `All ${MAX_EXAMINATIONS} examinations are already in use`}
            >
              + Add Examination
            </Button>
          </>
        )}
        <div style={{ flex: 1 }} />
        {footer}
      </div>
    </>
  );
}
