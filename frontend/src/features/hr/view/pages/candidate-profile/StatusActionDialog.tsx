import { ConfirmDialog } from "../../../../../shared/ui/ConfirmDialog";

export type StatusAction = "reopen" | "continue" | "reject_flagged";

/** "Are you sure?" before reopening an application or answering a flag
 *  (let continue, or reject): each changes where a real person stands. */
export function StatusActionDialog({
  confirmingAction,
  profile,
  onConfirm,
  onCancel,
}: {
  confirmingAction: StatusAction | null;
  profile: { applicant_name: string };
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <ConfirmDialog
      open={confirmingAction !== null}
      title={
        confirmingAction === "reopen"
          ? `Reopen ${profile.applicant_name}'s application?`
          : confirmingAction === "continue"
          ? `Let ${profile.applicant_name} continue?`
          : `Reject ${profile.applicant_name}'s application?`
      }
      description={
        confirmingAction === "reopen"
          ? "The application becomes active again, and the earlier decision stays on record."
          : confirmingAction === "continue"
          ? "This clears the review flag, so the application can move on to its next stage."
          : "This closes the application as rejected."
      }
      confirmLabel={
        confirmingAction === "reopen"
          ? "Reopen"
          : confirmingAction === "continue"
          ? "Approve to Continue"
          : "Reject Application"
      }
      confirmVariant={confirmingAction === "reject_flagged" ? "danger" : "primary"}
      width={440}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
}
