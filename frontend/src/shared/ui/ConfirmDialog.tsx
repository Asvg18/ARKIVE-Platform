import { useEffect, type ReactNode } from "react";
import { Button } from "./Button";
import { Card } from "./Card";

/** A small, reusable confirmation modal -- written generically since
 * any hard-to-reverse action (withdraw, delete, reject) should ask
 * before acting rather than fire on a single click. Built here rather
 * than inline so the next caller reuses it instead of hand-rolling
 * another overlay. */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Go Back",
  confirmVariant = "primary",
  confirming = false,
  confirmDisabled = false,
  hideCancel = false,
  width = 400,
  children,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** "danger" for an action that destroys something and can't be undone,
   *  so the button itself says so before it's pressed. Defaults to the
   *  ordinary primary, which every existing caller wants. */
  confirmVariant?: "primary" | "danger";
  confirming?: boolean;
  /** Lets a caller gate its own confirm (e.g. an unticked acknowledgement). */
  confirmDisabled?: boolean;
  /**
   * Drops the cancel button, for a dialog reporting something that has
   * already happened. "Cancel" next to a completed action offers to undo
   * something this component cannot undo.
   */
  hideCancel?: boolean;
  width?: number;
  /**
   * Optional body between the description and the buttons — a checklist,
   * a reason field, an acknowledgement. Added for the hire decision
   * dialog, which needs to show *what is missing* before HR confirms;
   * a plain string description could not carry that.
   */
  children?: ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      role="presentation"
      onClick={onCancel}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15, 23, 42, 0.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
        zIndex: 100,
      }}
    >
      <div role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title" onClick={(e) => e.stopPropagation()}>
        <Card padding={24} elevation="md" style={{ width, maxWidth: "90vw", maxHeight: "85vh", overflowY: "auto" }}>
          <h2
            id="confirm-dialog-title"
            style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xl)", fontWeight: 700, color: "var(--ink-900)", margin: 0 }}
          >
            {title}
          </h2>
          <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", marginTop: 10, lineHeight: 1.55 }}>
            {description}
          </p>
          {children}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 24 }}>
            {!hideCancel && (
              <Button variant="secondary" onClick={onCancel} disabled={confirming}>
                {cancelLabel}
              </Button>
            )}
            <Button variant={confirmVariant} onClick={onConfirm} disabled={confirming || confirmDisabled}>
              {confirming ? "Working..." : confirmLabel}
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
