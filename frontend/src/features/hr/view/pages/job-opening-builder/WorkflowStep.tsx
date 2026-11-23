import type { Dispatch, SetStateAction } from "react";
import type { WorkflowIssue, WorkflowPreset } from "../../../../../shared/api/pipeline";
import { Button } from "../../../../../shared/ui/Button";
import { ArrowRightIcon } from "../../../../../shared/ui/icons";
import { Alert } from "../../../../../shared/ui/Alert";
import { WorkflowStagesEditor } from "../../components/WorkflowStagesEditor";
import type { WorkflowStageDraft } from "../../../model/workflowStages";
import { StepFrame } from "./wizard";
import { WORKFLOW_PRESETS } from "./builderModel";

export function WorkflowStep({
  preset,
  onPresetChange,
  stages,
  onStagesChange,
  roundLabels,
  onRoundLabelsChange,
  examLabels,
  onExamLabelsChange,
  onIssuesChange,
  canSave,
  pending,
  error,
  onBack,
  onSave,
  onSaveDraft,
}: {
  preset: WorkflowPreset;
  onPresetChange: (p: WorkflowPreset) => void;
  stages: WorkflowStageDraft[];
  onStagesChange: Dispatch<SetStateAction<WorkflowStageDraft[]>>;
  roundLabels: Record<string, string>;
  onRoundLabelsChange: Dispatch<SetStateAction<Record<string, string>>>;
  examLabels: Record<string, string>;
  onExamLabelsChange: Dispatch<SetStateAction<Record<string, string>>>;
  onIssuesChange: (issues: WorkflowIssue[]) => void;
  canSave: boolean;
  pending: "publish" | "draft" | null;
  error: string | null;
  onBack: () => void;
  onSave: () => void;
  onSaveDraft: () => void;
}) {
  const busy = pending != null;
  return (
    <StepFrame
      title="Set the hiring workflow"
      sub="Start from a template, then adjust the stages for this role. Save the workflow to continue."
      back={
        <Button variant="secondary" onClick={onBack} disabled={busy}>
          Back
        </Button>
      }
      note={!canSave && "Fix the workflow's errors to save it"}
      actions={
        <>
          <Button variant="secondary" disabled={busy} onClick={onSaveDraft}>
            {pending === "draft" ? "Saving…" : "Save as draft"}
          </Button>
          <Button variant="primary" disabled={busy || !canSave} onClick={onSave}>
            Save workflow
            <ArrowRightIcon width={15} height={15} aria-hidden="true" />
          </Button>
        </>
      }
    >
      <div className="ark-choices" role="radiogroup" aria-label="Start from a template">
        {WORKFLOW_PRESETS.map((option) => (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={preset === option.id}
            disabled={busy}
            className="ark-choice"
            onClick={() => onPresetChange(option.id)}
          >
            <span className="ark-choice__text">
              <span className="ark-choice__title">
                {option.title}
                <span className="ark-choice__count">{option.stages.length} stages</span>
              </span>
              <span className="ark-choice__desc">{option.description}</span>
            </span>
            <span className="ark-choice__radio" aria-hidden="true" />
          </button>
        ))}
      </div>
      <p className="ark-wizard__aside-note">Choosing a template replaces the stages below.</p>

      <WorkflowStagesEditor
        stages={stages}
        onStagesChange={onStagesChange}
        roundLabels={roundLabels}
        onRoundLabelsChange={onRoundLabelsChange}
        examLabels={examLabels}
        onExamLabelsChange={onExamLabelsChange}
        onIssuesChange={onIssuesChange}
      />

      {error && <Alert tone="danger" title={error} />}
    </StepFrame>
  );
}
