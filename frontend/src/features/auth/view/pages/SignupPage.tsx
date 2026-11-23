import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../controller/AuthContext";
import { afterSignInPath } from "../../model/roleHome";
import { ApiError } from "../../../../shared/api/client";
import { Card } from "../../../../shared/ui/Card";
import { Button } from "../../../../shared/ui/Button";
import { Logo } from "../../../../shared/ui/Logo";
import { FormError, TextField } from "../components/AuthFields";
import {
  SIGNUP_FIELDS,
  joinFullName,
  signupErrorFromServer,
  validateSignup,
  validateSignupField,
  type SignupErrors,
  type SignupField,
  type SignupValues,
} from "../../model/signupValidation";

const EMPTY: SignupValues = { firstName: "", lastName: "", email: "", password: "", confirmPassword: "" };

/**
 * Applicant self-registration.
 *
 * Errors are shown at the field they belong to, the way sign-up forms
 * generally do it: a field is checked when it is left (if something was
 * typed), every field is checked on submit and the first one needing
 * attention takes focus, and a message clears the moment its field is
 * put right rather than waiting for the next submit. The browser's own
 * validation bubbles are turned off (`noValidate`) so there is one voice,
 * not two. Only what belongs to no field — a timeout, a rate limit, a
 * server fault — shows as a message over the button.
 */
export function SignupPage() {
  const { signup, user } = useAuth();
  const navigate = useNavigate();
  // A page that sent them here to sign in (the job board's "browse all
  // positions") is where they land afterwards; see afterSignInPath.
  const next = useSearchParams()[0].get("next");
  const loginHref = next ? `/login?next=${encodeURIComponent(next)}` : "/login";

  const [values, setValues] = useState<SignupValues>(EMPTY);
  const [errors, setErrors] = useState<SignupErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  // The server said the address is already registered: its message gets
  // a way through to signing in, until the address is changed.
  const [emailTaken, setEmailTaken] = useState(false);
  const [loading, setLoading] = useState(false);
  const [submittedEmail, setSubmittedEmail] = useState<string | null>(null);
  const [resending, setResending] = useState(false);
  const [resendMessage, setResendMessage] = useState<string | null>(null);
  const inputs = useRef<Partial<Record<SignupField, HTMLInputElement | null>>>({});

  useEffect(() => {
    if (user) navigate(afterSignInPath(user.role, next), { replace: true });
  }, [user, navigate, next]);

  function update(field: SignupField, value: string) {
    const nextValues = { ...values, [field]: value };
    setValues(nextValues);
    if (field === "email") setEmailTaken(false);
    setErrors((prev) => {
      const updated = { ...prev };
      // A field already showing a message is re-checked as it is typed,
      // so the message goes as soon as the mistake does.
      if (prev[field]) updated[field] = validateSignupField(field, nextValues);
      // Fields whose rule reads another field's value follow it.
      if (field === "password" && prev.confirmPassword) {
        updated.confirmPassword = validateSignupField("confirmPassword", nextValues);
      }
      if (field === "email" && prev.password) {
        updated.password = validateSignupField("password", nextValues);
      }
      return updated;
    });
  }

  function leave(field: SignupField) {
    // Leaving an empty field is not yet a mistake — tabbing past it is
    // how people move through a form. It is reported on submit.
    if (!values[field] && !errors[field]) return;
    setErrors((prev) => ({ ...prev, [field]: validateSignupField(field, values) }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);

    const found = validateSignup(values);
    setErrors(found);
    const firstInvalid = SIGNUP_FIELDS.find((f) => found[f]);
    if (firstInvalid) {
      inputs.current[firstInvalid]?.focus();
      return;
    }

    setLoading(true);
    try {
      await signup(values.email.trim(), values.password, joinFullName(values.firstName, values.lastName));
      setSubmittedEmail(values.email.trim());
    } catch (err) {
      if (!(err instanceof ApiError)) {
        setFormError("Something went wrong. Please try again.");
        return;
      }

      const result = signupErrorFromServer(err.status, err.detail, err.message);
      if (result.field) {
        const field = result.field;
        setErrors((prev) => ({ ...prev, [field]: result.message }));
        setEmailTaken(result.kind === "duplicate-email");
        inputs.current[field]?.focus();
      } else {
        setFormError(result.message);
      }

    } finally {
      setLoading(false);
    }
  }

  async function resendVerification() {
    if (!submittedEmail) return;
    setResending(true);
    setResendMessage(null);
    try {
      await fetch(`${import.meta.env.VITE_API_BASE_URL}/auth/resend-verification`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: submittedEmail }),
      });
      setResendMessage("If an account exists for that email, a new verification link has been sent.");
    } catch {
      setResendMessage("We couldn't resend the email. Please try again.");
    } finally {
      setResending(false);
    }
  }

  const bind = (field: SignupField) => ({
    id: `signup-${field}`,
    value: values[field],
    error: errors[field],
    onChange: (value: string) => update(field, value),
    onBlur: () => leave(field),
    inputRef: (el: HTMLInputElement | null) => {
      inputs.current[field] = el;
    },
  });

  return (
    <div className="ark-auth">
      <div className="ark-auth__panel">
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, marginBottom: 28 }}>
          <Logo size={46} />
          <span style={{ fontSize: "var(--text-xl)", fontWeight: 800, color: "var(--ink-900)", letterSpacing: "-0.3px" }}>
            ARKIVE
          </span>
          <span style={{ fontSize: "var(--text-sm)", color: "var(--ink-600)" }}>Create your applicant account</span>
        </div>

        <Card padding={28} elevation="md">
          {submittedEmail ? (
            <div style={{ fontSize: "var(--text-sm)", lineHeight: 1.6 }}>
              <h2 style={{ margin: 0, color: "var(--ink-900)", fontSize: "var(--text-lg)" }}>Check your email</h2>
              <p style={{ margin: "12px 0", color: "var(--ink-700)" }}>
                We sent a verification link to <strong>{submittedEmail}</strong>. Verify your email before signing in.
              </p>
              {resendMessage && <p role="status" style={{ color: "var(--success-text)" }}>{resendMessage}</p>}
              <Button type="button" variant="secondary" onClick={resendVerification} disabled={resending} style={{ width: "100%" }}>
                {resending ? "Sending..." : "Resend verification email"}
              </Button>
            </div>
          ) : (
          <form onSubmit={handleSubmit} noValidate style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            {/* Side by side while there is room, stacked on a narrow phone. */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "18px 12px" }}>
              <TextField label="First name" autoComplete="given-name" {...bind("firstName")} />
              <TextField label="Last name" autoComplete="family-name" {...bind("lastName")} />
            </div>

            <TextField
              label="Email"
              type="email"
              autoComplete="email"
              {...bind("email")}
              errorExtra={
                emailTaken && (
                  <>
                    {" "}
                    <a href={loginHref} style={{ color: "inherit", fontWeight: 700, textDecoration: "underline", whiteSpace: "nowrap" }}>
                      Sign in instead
                    </a>
                  </>
                )
              }
            />

            {/* The backend requires 8 characters. Saying so here, before
                the field is filled in, is the difference between a rule
                and a rejection. */}
            <TextField
              label="Password"
              type="password"
              autoComplete="new-password"
              hint="At least 8 characters."
              {...bind("password")}
            />

            <TextField label="Confirm password" type="password" autoComplete="new-password" {...bind("confirmPassword")} />

            {formError && <FormError message={formError} />}

            <Button type="submit" variant="primary" disabled={loading} style={{ width: "100%", padding: "12px 20px" }}>
              {loading ? "Creating account..." : "Create account"}
            </Button>
          </form>
          )}
        </Card>

        <p style={{ textAlign: "center", fontSize: "var(--text-sm)", color: "var(--ink-400)", marginTop: 20 }}>
          Already have an account?{" "}
          <a href={loginHref} style={{ color: "var(--accent)", textDecoration: "none", fontWeight: 600 }}>
            Sign in
          </a>
        </p>
        <p style={{ textAlign: "center", fontSize: "var(--text-sm)", color: "var(--ink-400)", marginTop: 8 }}>
          <a href="/" style={{ color: "var(--ink-600)", textDecoration: "none" }}>
            &larr; Back to job board
          </a>
        </p>
      </div>
    </div>
  );
}
