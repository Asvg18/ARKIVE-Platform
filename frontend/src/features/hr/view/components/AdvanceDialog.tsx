/** "Are you sure?" in front of every move to the next stage. */

import { ConfirmDialog } from "../../../../shared/ui/ConfirmDialog";

/** Shown for every advance, from the Candidate Profile's Advance (and
 * Skip), the HR Workflow list's Advance, or a card dropped on the board: a
 * misclick moves a real person, so no advance is one click. It decides
 * nothing; confirming sends the same transition request, and if the stage
 * being left is incomplete the server's refusal opens StageAdvanceDialog. */
export function AdvanceDialog({
  open,
  candidateName,
  fromStageLabel,
  targetStageLabel,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  candidateName: string;
  fromStageLabel: string;
  targetStageLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <ConfirmDialog
      open={open}
      title={`Move ${candidateName} to ${targetStageLabel}?`}
      description={`${candidateName} will move from ${fromStageLabel} to ${targetStageLabel}, and their application will show the new stage.`}
      // The title already names the stage -- a per-job round name can run
      // long enough to push Go Back out of a button row that repeats it.
      confirmLabel="Advance"
      width={440}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
}
