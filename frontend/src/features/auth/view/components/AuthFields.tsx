import type { ChangeEvent, ReactNode } from "react";
import { AlertIcon } from "../../../../shared/ui/icons";
import { PasswordInput } from "../../../../shared/ui/PasswordInput";
import { authFieldError, authHint, authInputInvalid, authInputStyle, authLabel } from "../styles/authStyles";

/* The pieces of the two forms that create an account -- sign up, and
 * accept an invitation. Lifted out of the sign-up page once the
 * invitation form needed the same ones, so the two can't drift: a name
 * or password field looks, checks and fails the same way on both. */

/** One labelled input with its hint, or — when it has failed a check —
 * its error in the hint's place, tied to the input for screen readers
 * through aria-describedby and aria-invalid. */
export function TextField({
  id,
  label,
  type = "text",
  value,
  error,
  errorExtra,
  hint,
  autoComplete,
  onChange,
  onBlur,
  inputRef,
}: {
  id: string;
  label: string;
  type?: string;
  value: string;
  error?: string;
  errorExtra?: ReactNode;
  hint?: string;
  autoComplete?: string;
  onChange: (value: string) => void;
  onBlur: () => void;
  inputRef: (el: HTMLInputElement | null) => void;
}) {
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  const inputStyle = error ? { ...authInputStyle, ...authInputInvalid } : authInputStyle;
  const shared = {
    id,
    value,
    onChange: (e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value),
    onBlur,
    autoComplete,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": describedBy,
    style: inputStyle,
  };
  return (
    <div style={{ minWidth: 0 }}>
      <label style={authLabel} htmlFor={id}>
        {label}
      </label>
      {type === "password" ? (
        <PasswordInput {...shared} inputRef={inputRef} />
      ) : (
        <div>
          <input {...shared} ref={inputRef} type={type} />
        </div>
      )}
      {error ? (
        <p id={`${id}-error`} style={authFieldError}>
          <AlertIcon width={13} height={13} style={{ flexShrink: 0, marginTop: 1.5 }} aria-hidden="true" />
          <span>
            {error}
            {errorExtra}
          </span>
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} style={authHint}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/** What went wrong that belongs to no field — a timeout, a rate limit, a
 * server fault — shown over the form's button. */
export function FormError({ message }: { message: string }) {
  return (
    <div
      role="alert"
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 8,
        background: "var(--danger-bg)",
        color: "var(--danger-text)",
        borderRadius: "var(--radius)",
        padding: "10px 12px",
        fontSize: "var(--text-sm)",
        fontWeight: 600,
        lineHeight: 1.45,
      }}
    >
      <AlertIcon width={15} height={15} style={{ flexShrink: 0, marginTop: 1.5 }} aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}
