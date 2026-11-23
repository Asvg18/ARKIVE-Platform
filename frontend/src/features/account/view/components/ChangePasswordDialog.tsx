import { useEffect, useState } from "react";
import { useAuth } from "../../../auth/controller/AuthContext";
import { ApiError, apiFetch } from "../../../../shared/api/client";
import { ConfirmDialog } from "../../../../shared/ui/ConfirmDialog";
import { PasswordInput } from "../../../../shared/ui/PasswordInput";

/** Lets a signed-in person change their own password, from anywhere in
 * the app. Reaches into auth context for the token the same way
 * NotificationBell does, so the three app shells need no wiring of
 * their own beyond opening it.
 *
 * Built on ConfirmDialog rather than a second overlay: the escape /
 * click-outside / focus behaviour is already solved there, and a
 * password form is a confirmation with more fields.
 *
 * The confirm field is checked here and never sent. The server has no
 * way to catch a mistyped new password -- it only ever receives one --
 * and a typo would otherwise lock the person out of an account with no
 * reset flow to recover it. */
export function ChangePasswordDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { token } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [changed, setChanged] = useState(false);

  // Reopening must never show the last attempt's typing or its error.
  useEffect(() => {
    if (open) {
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setError(null);
      setSaving(false);
      setChanged(false);
    }
  }, [open]);

  async function submit() {
    if (newPassword !== confirmPassword) {
      setError("The new passwords do not match.");
      return;
    }
    setError(null);
    setSaving(true);
    try {
      await apiFetch<void>("/auth/change-password", {
        method: "POST",
        token,
        body: { current_password: currentPassword, new_password: newPassword },
      });
      setChanged(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change your password.");
    } finally {
      setSaving(false);
    }
  }

  const canSubmit = Boolean(currentPassword && newPassword && confirmPassword);

  if (changed) {
    return (
      <ConfirmDialog
        open={open}
        title="Password changed"
        description="Your new password is active. You will use it the next time you sign in."
        confirmLabel="Done"
        hideCancel
        onConfirm={onClose}
        onCancel={onClose}
        width={420}
      />
    );
  }

  return (
    <ConfirmDialog
      open={open}
      title="Change password"
      description="Enter your current password, then choose a new one."
      confirmLabel="Update password"
      cancelLabel="Cancel"
      confirming={saving}
      confirmDisabled={!canSubmit}
      onConfirm={submit}
      onCancel={onClose}
      width={420}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 18 }}>
        <Field
          id="cpw-current"
          label="Current password"
          value={currentPassword}
          autoComplete="current-password"
          onChange={setCurrentPassword}
        />
        <Field
          id="cpw-new"
          label="New password"
          value={newPassword}
          autoComplete="new-password"
          hint="At least 8 characters."
          onChange={setNewPassword}
        />
        <Field
          id="cpw-confirm"
          label="Confirm new password"
          value={confirmPassword}
          autoComplete="new-password"
          onChange={setConfirmPassword}
          onEnter={() => canSubmit && submit()}
        />

        {error && (
          <div
            style={{
              background: "var(--warning-bg)",
              color: "var(--warning-text)",
              borderRadius: "var(--radius)",
              padding: "10px 12px",
              fontSize: "var(--text-sm)",
              fontWeight: 600,
            }}
          >
            {error}
          </div>
        )}
      </div>
    </ConfirmDialog>
  );
}

function Field({
  id,
  label,
  value,
  hint,
  autoComplete,
  onChange,
  onEnter,
}: {
  id: string;
  label: string;
  value: string;
  hint?: string;
  autoComplete: string;
  onChange: (next: string) => void;
  onEnter?: () => void;
}) {
  return (
    <div>
      <label
        htmlFor={id}
        style={{
          display: "block",
          fontSize: "var(--text-xs)",
          fontWeight: 700,
          color: "var(--ink-600)",
          textTransform: "uppercase",
          letterSpacing: "0.04em",
          marginBottom: 6,
        }}
      >
        {label}
      </label>
      {/* Border, hover and focus ring all come from the global input
          rule in styles/base.css -- only the box model is set here. */}
      <PasswordInput
        id={id}
        value={value}
        autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && onEnter) {
            e.preventDefault();
            onEnter();
          }
        }}
        style={{ display: "block", width: "100%", boxSizing: "border-box" }}
      />
      {hint && (
        <p style={{ fontSize: "var(--text-xs)", color: "var(--ink-400)", margin: "6px 0 0" }}>{hint}</p>
      )}
    </div>
  );
}
