import { stageLabel } from "../../../../../shared/lib/stageLabels";
import { Button } from "../../../../../shared/ui/Button";
import { Alert } from "../../../../../shared/ui/Alert";
import { StepFrame } from "./wizard";

export function PublishStep({
  title,
  department,
  applicationDeadline,
  stages,
  roundLabels,
  examLabels,
  questionCount,
  gaps,
  pending,
  error,
  onBack,
  onPublish,
  onSaveDraft,
}: {
  title: string;
  department: string;
  applicationDeadline: string;
  stages: string[];
  roundLabels: Record<string, string>;
  examLabels: Record<string, string>;
  /** null when the workflow has no Pre-Screening, so no questions apply. */
  questionCount: number | null;
  /** What still blocks publishing; empty when it's ready. */
  gaps: string[];
  pending: "publish" | "draft" | null;
  error: string | null;
  onBack: () => void;
  onPublish: () => void;
  onSaveDraft: () => void;
}) {
  const busy = pending != null;
  const closes = applicationDeadline
    ? new Date(`${applicationDeadline}T00:00:00`).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "Not set";
  const nameOf = (stage: string) => roundLabels[stage]?.trim() || examLabels[stage]?.trim() || stageLabel(stage);

  return (
    <StepFrame
      title="Review and publish"
      sub="Check the job one last time. Publish it now, or save it as a draft to finish later."
      back={
        <Button variant="secondary" onClick={onBack} disabled={busy}>
          Back
        </Button>
      }
      note={gaps.length > 0 && "Finish the items above to publish (a draft doesn't need them)"}
      actions={
        <>
          <Button variant="secondary" disabled={busy} onClick={onSaveDraft}>
            {pending === "draft" ? "Saving…" : "Save as draft"}
          </Button>
          <Button variant="primary" disabled={busy || gaps.length > 0} onClick={onPublish}>
            {pending === "publish" ? "Publishing…" : "Publish job opening"}
          </Button>
        </>
      }
    >
      {/* What is about to be created, so the last step can be checked
          without walking back through the others. */}
      <dl className="ark-summary">
        <div>
          <dt>Job title</dt>
          <dd title={title}>{title}</dd>
        </div>
        <div>
          <dt>Department</dt>
          <dd title={department}>{department}</dd>
        </div>
        <div>
          <dt>Applications close</dt>
          <dd>{closes}</dd>
        </div>
        <div>
          <dt>Pre-screening questions</dt>
          <dd>{questionCount === null ? "Not used" : questionCount}</dd>
        </div>
      </dl>

      <span className="ark-flow" aria-label="Hiring workflow">
        {stages.map((stage, i) => (
          <span key={stage} className="ark-flow__stage">
            <span className="ark-flow__n">{i + 1}</span>
            {nameOf(stage)}
          </span>
        ))}
      </span>

      {gaps.length > 0 ? (
        <Alert tone="warning" title="Before this can be published">
          <ul className="ark-alert__body" style={{ margin: 0, paddingLeft: 18 }}>
            {gaps.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </Alert>
      ) : (
        <Alert tone="success" title="Ready to publish" />
      )}

      {error && <Alert tone="danger" title={error} />}
    </StepFrame>
  );
}
