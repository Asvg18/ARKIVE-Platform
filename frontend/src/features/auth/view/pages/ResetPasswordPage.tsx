import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../../controller/AuthContext";
import { ApiError, apiFetch } from "../../../../shared/api/client";
import { Card } from "../../../../shared/ui/Card";
import { Button } from "../../../../shared/ui/Button";
import { Logo } from "../../../../shared/ui/Logo";
import { PasswordInput } from "../../../../shared/ui/PasswordInput";
import { authHint, authInputStyle, authLabel } from "../styles/authStyles";

type LinkState = "checking" | "valid" | "expired" | "used" | "unknown";

const DEAD_LINK_MESSAGE: Record<Exclude<LinkState, "checking" | "valid">, string> = {
  expired: "This reset link has expired. Reset links last one hour.",
  used: "This reset link has already been used.",
  unknown: "This reset link is not valid. It may have been mistyped or replaced by a newer one.",
};

/** "I forgot my password", step two.
 *
 * Checks the link *before* showing the form. A stale link that only
 * failed on submit would mean choosing a password, confirming it, and
 * only then being told none of it counted. */
export function ResetPasswordPage() {
  const { token } = useParams<{ token: string }>();
  const { resetPassword } = useAuth();
  const navigate = useNavigate();

  const [linkState, setLinkState] = useState<LinkState>("checking");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!token) {
      setLinkState("unknown");
      return;
    }
    apiFetch<{ status: LinkState }>(`/auth/reset-password/${token}`)
      .then((res) => setLinkState(res.status))
      .catch(() => setLinkState("unknown"));
  }, [token]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    if (password !== confirmPassword) {
      setError("The passwords do not match.");
      return;
    }
    setError(null);
    setSaving(true);
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="ark-auth">
      <div className="ark-auth__panel">
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, marginBottom: 28 }}>
          <Logo size={46} />
          <span style={{ fontSize: "var(--text-xl)", fontWeight: 800, color: "var(--ink-900)", letterSpacing: "-0.3px" }}>
            ARKIVE
          </span>
          <span style={{ fontSize: "var(--text-sm)", color: "var(--ink-600)" }}>Choose a new password</span>
        </div>

        <Card padding={28} elevation="md">
          {linkState === "checking" && (
            <p style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--ink-600)" }}>
              Checking your link...
            </p>
          )}

          {linkState !== "checking" && linkState !== "valid" && (
            <div style={{ fontSize: "var(--text-sm)", lineHeight: 1.6 }}>
              <p style={{ margin: 0, fontWeight: 600, color: "var(--ink-900)" }}>
                {DEAD_LINK_MESSAGE[linkState]}
              </p>
              <p style={{ margin: "10px 0 0", color: "var(--ink-600)" }}>
                Request a new one and it will arrive in a moment.
              </p>
              <Button
                variant="primary"
                onClick={() => navigate("/forgot-password")}
                style={{ width: "100%", padding: "12px 20px", marginTop: 18 }}
              >
                Request a new link
              </Button>
            </div>
          )}

          {linkState === "valid" && !done && (
            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 18 }}>
              <div>
                <label style={authLabel} htmlFor="reset-password">
                  New password
                </label>
                <PasswordInput
                  id="reset-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  autoComplete="new-password"
                  style={authInputStyle}
                />
                <p style={authHint}>At least 8 characters.</p>
              </div>
              <div>
                <label style={authLabel} htmlFor="reset-confirm-password">
                  Confirm new password
                </label>
                <PasswordInput
                  id="reset-confirm-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  autoComplete="new-password"
                  style={authInputStyle}
                />
              </div>

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

              <Button type="submit" variant="primary" disabled={saving} style={{ width: "100%", padding: "12px 20px" }}>
                {saving ? "Saving..." : "Set new password"}
              </Button>
            </form>
          )}

          {done && (
            <div
              role="status"
              style={{
                background: "var(--surface-bg)",
                color: "var(--ink-900)",
                border: "1px solid var(--surface-border)",
                borderRadius: "var(--radius)",
                padding: "12px",
                fontSize: "var(--text-sm)",
                lineHeight: 1.6,
              }}
            >
              <strong>Your password is now changed.</strong>
              <p style={{ margin: "8px 0 16px", color: "var(--ink-700)" }}>
                Please sign in with your new password to continue.
              </p>
              <Button
                variant="primary"
                onClick={() => navigate("/login", { replace: true })}
                style={{ width: "100%", padding: "12px 20px" }}
              >
                Go to sign in
              </Button>
            </div>
          )}
        </Card>

        <p style={{ textAlign: "center", fontSize: "var(--text-sm)", color: "var(--ink-400)", marginTop: 20 }}>
          <a href="/login" style={{ color: "var(--accent)", textDecoration: "none", fontWeight: 600 }}>
            Back to sign in
          </a>
        </p>
      </div>
    </div>
  );
}
