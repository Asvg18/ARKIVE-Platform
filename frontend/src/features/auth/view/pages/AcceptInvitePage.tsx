import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../../controller/AuthContext";
import { roleHomePath } from "../../model/roleHome";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { InviteStatus } from "../../../../shared/api/invites";
import { Card } from "../../../../shared/ui/Card";
import { Button } from "../../../../shared/ui/Button";
import { Logo } from "../../../../shared/ui/Logo";
import { FormError, TextField } from "../components/AuthFields";
import { authInputStyle, authLabel } from "../styles/authStyles";
import {
  INVITE_FIELDS,
  inviteErrorFromServer,
  joinFullName,
  validateSignup,
  validateSignupField,
  type SignupErrors,
  type SignupField,
  type SignupValues,
} from "../../model/signupValidation";

const ROLE_LABEL: Record<InviteStatus["role"], string> = {
  hr_admin: "HR Admin",
  evaluator: "Evaluator",
};

const EMPTY: SignupValues = { firstName: "", lastName: "", email: "", password: "", confirmPassword: "" };

/**
 * Where an invited HR admin or evaluator sets up their account, from the
 * link in their invitation -- the first super admin too, whose
 * invitation comes from the setup step.
 *
 * The form is sign-up's less the email, which the invitation fixed:
 * first and last name asked for separately and joined into the one name
 * the account keeps, the same rules, and errors shown at the field they
 * belong to in the same way (see SignupPage).
 */
export function AcceptInvitePage() {
  const { token: inviteToken } = useParams<{ token: string }>();
  const { acceptInvite, user } = useAuth();
  const navigate = useNavigate();

  const [invite, setInvite] = useState<InviteStatus | null>(null);
  const [resolving, setResolving] = useState(true);
  const [notFound, setNotFound] = useState(false);

  const [values, setValues] = useState<SignupValues>(EMPTY);
  const [errors, setErrors] = useState<SignupErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const inputs = useRef<Partial<Record<SignupField, HTMLInputElement | null>>>({});

  useEffect(() => {
    if (user) navigate(roleHomePath(user.role), { replace: true });
  }, [user, navigate]);

  useEffect(() => {
    if (!inviteToken) return;
    apiFetch<InviteStatus>(`/invites/${inviteToken}`)
      .then((found) => {
        setInvite(found);
        // Not typed here, but the password may not be the same as it.
        setValues((prev) => ({ ...prev, email: found.email }));
      })
      .catch(() => setNotFound(true))
      .finally(() => setResolving(false));
  }, [inviteToken]);

  function update(field: SignupField, value: string) {
    const nextValues = { ...values, [field]: value };
    setValues(nextValues);
    setErrors((prev) => {
      const updated = { ...prev };
      if (prev[field]) updated[field] = validateSignupField(field, nextValues);
      if (field === "password" && prev.confirmPassword) {
        updated.confirmPassword = validateSignupField("confirmPassword", nextValues);
      }
      return updated;
    });
  }

  function leave(field: SignupField) {
    if (!values[field] && !errors[field]) return;
    setErrors((prev) => ({ ...prev, [field]: validateSignupField(field, values) }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!inviteToken) return;
    setFormError(null);

    const found = validateSignup(values, INVITE_FIELDS);
    setErrors(found);
    const firstInvalid = INVITE_FIELDS.find((f) => found[f]);
    if (firstInvalid) {
      inputs.current[firstInvalid]?.focus();
      return;
    }

    setSubmitting(true);
    try {
      await acceptInvite(inviteToken, joinFullName(values.firstName, values.lastName), values.password);
    } catch (err) {
      if (!(err instanceof ApiError)) {
        setFormError("Something went wrong. Please try again.");
        return;
      }
      const result = inviteErrorFromServer(err.status, err.detail, err.message);
      if (result.field) {
        const field = result.field;
        setErrors((prev) => ({ ...prev, [field]: result.message }));
        inputs.current[field]?.focus();
      } else {
        setFormError(result.message);
      }
    } finally {
      setSubmitting(false);
    }
  }

  const bind = (field: SignupField) => ({
    id: `invite-${field}`,
    value: values[field],
    error: errors[field],
    onChange: (value: string) => update(field, value),
    onBlur: () => leave(field),
    inputRef: (el: HTMLInputElement | null) => {
      inputs.current[field] = el;
    },
  });

  return (
    <div
      className="ark-auth"
    >
      <div className="ark-auth__panel">
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, marginBottom: 28 }}>
          <Logo size={46} />
          <span style={{ fontSize: "var(--text-xl)", fontWeight: 800, color: "var(--ink-900)", letterSpacing: "-0.3px" }}>
            ARKIVE
          </span>
          <span style={{ fontSize: "var(--text-sm)", color: "var(--ink-600)" }}>
            {invite
              ? `You're invited as ${invite.role === "hr_admin" && invite.super_admin ? "Super Admin" : ROLE_LABEL[invite.role]}`
              : "Accept your invite"}
          </span>
        </div>

        <Card padding={28} elevation="md">
          {resolving && (
            <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", margin: 0 }}>
              Checking your invite...
            </p>
          )}

          {!resolving && (notFound || !invite) && (
            <InviteMessage
              title="This invite link isn't valid."
              body="Double-check the link, or ask an HR admin to send a new one."
            />
          )}

          {!resolving && invite?.status === "expired" && (
            <InviteMessage
              title="This invite has expired."
              body="Invites are valid for 7 days. Ask an HR admin to send you a new one."
            />
          )}

          {!resolving && invite?.status === "revoked" && (
            <InviteMessage
              title="This invite was revoked."
              body="Ask an HR admin to send you a new one if this was a mistake."
            />
          )}

          {!resolving && invite?.status === "accepted" && (
            <InviteMessage
              title="This invite has already been used."
              body="If that was you, sign in instead."
              linkHref="/login"
              linkLabel="Go to sign in"
            />
          )}

          {!resolving && invite?.status === "pending" && (
            <form onSubmit={handleSubmit} noValidate style={{ display: "flex", flexDirection: "column", gap: 18 }}>
              <div>
                <label style={authLabel}>Email</label>
                <div
                  style={{
                    ...authInputStyle,
                    background: "var(--surface-bg)",
                    color: "var(--ink-600)",
                  }}
                >
                  {invite.email}
                </div>
              </div>

              {/* Side by side while there is room, stacked on a narrow phone. */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "18px 12px" }}>
                <TextField label="First name" autoComplete="given-name" {...bind("firstName")} />
                <TextField label="Last name" autoComplete="family-name" {...bind("lastName")} />
              </div>

              <TextField
                label="Password"
                type="password"
                autoComplete="new-password"
                hint="At least 8 characters."
                {...bind("password")}
              />

              <TextField label="Confirm password" type="password" autoComplete="new-password" {...bind("confirmPassword")} />

              {formError && <FormError message={formError} />}

              <Button
                type="submit"
                variant="primary"
                disabled={submitting}
                style={{ width: "100%", padding: "12px 20px" }}
              >
                {submitting ? "Creating account..." : "Accept invite & create account"}
              </Button>
            </form>
          )}
        </Card>
      </div>
    </div>
  );
}

function InviteMessage({
  title,
  body,
  linkHref,
  linkLabel,
}: {
  title: string;
  body: string;
  linkHref?: string;
  linkLabel?: string;
}) {
  return (
    <div>
      <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", fontWeight: 700, color: "var(--ink-900)", margin: 0 }}>
        {title}
      </p>
      <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", marginTop: 8, marginBottom: 0 }}>
        {body}
      </p>
      {linkHref && linkLabel && (
        <a
          href={linkHref}
          style={{ display: "inline-block", marginTop: 16, color: "var(--accent)", fontWeight: 600, fontSize: "var(--text-sm)", textDecoration: "none" }}
        >
          {linkLabel} &rarr;
        </a>
      )}
    </div>
  );
}


