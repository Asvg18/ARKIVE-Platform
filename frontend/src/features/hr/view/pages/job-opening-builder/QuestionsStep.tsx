import type { Dispatch, SetStateAction } from "react";
import type { PreScreeningQuestion } from "../../../../../shared/api/pipeline";
import { Button } from "../../../../../shared/ui/Button";
import { ArrowRightIcon } from "../../../../../shared/ui/icons";
import { Alert } from "../../../../../shared/ui/Alert";
import { PreScreeningQuestionsEditor } from "../../components/PreScreeningQuestionsEditor";
import { StepFrame } from "./wizard";

export function QuestionsStep({
  questions,
  onChange,
  complete,
  pending,
  error,
  onBack,
  onNext,
  onSaveDraft,
}: {
  questions: PreScreeningQuestion[];
  onChange: Dispatch<SetStateAction<PreScreeningQuestion[]>>;
  complete: boolean;
  pending: "publish" | "draft" | null;
  error: string | null;
  onBack: () => void;
  onNext: () => void;
  onSaveDraft: () => void;
}) {
  const busy = pending != null;
  return (
    <StepFrame
      title="Write the pre-screening questions"
      sub="Every applicant answers these during Pre-Screening, in this order. A job needs at least one before it can be published."
      back={
        <Button variant="secondary" onClick={onBack} disabled={busy}>
          Back
        </Button>
      }
      note={!complete && "Fill in or remove any empty question"}
      actions={
        <>
          <Button variant="secondary" disabled={busy} onClick={onSaveDraft}>
            {pending === "draft" ? "Saving…" : "Save as draft"}
          </Button>
          <Button variant="primary" disabled={busy || !complete} onClick={onNext}>
            Continue
            <ArrowRightIcon width={15} height={15} aria-hidden="true" />
          </Button>
        </>
      }
    >
      <PreScreeningQuestionsEditor questions={questions} onChange={onChange} />
      {error && <Alert tone="danger" title={error} />}
    </StepFrame>
  );
}
