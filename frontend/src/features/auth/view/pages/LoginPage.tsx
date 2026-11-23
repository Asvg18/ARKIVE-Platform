import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../controller/AuthContext";
import { afterSignInPath } from "../../model/roleHome";
import { ApiError } from "../../../../shared/api/client";
import { Card } from "../../../../shared/ui/Card";
import { Button } from "../../../../shared/ui/Button";
import { Logo } from "../../../../shared/ui/Logo";
import { PasswordInput } from "../../../../shared/ui/PasswordInput";
import { authInputStyle, authLabel } from "../styles/authStyles";

export function LoginPage() {
  const { login, user, sessionExpired } = useAuth();
  const navigate = useNavigate();
  // A page that sent them here to sign in (the job board's "browse all
  // positions") is where they land afterwards; see afterSignInPath.
  const [searchParams] = useSearchParams();
  const next = searchParams.get("next");
  // Set by Account Settings after an applicant deletes their account.
  const accountDeleted = searchParams.get("deleted") === "1";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [needsVerification, setNeedsVerification] = useState(false);
  const [resending, setResending] = useState(false);
  const [resendMessage, setResendMessage] = useState<string | null>(null);

  // Once login() resolves and the token lands in context, send the user
  // to the dashboard their role actually owns.
  useEffect(() => {
    if (user) navigate(afterSignInPath(user.role, next), { replace: true });
  }, [user, navigate, next]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setNeedsVerification(false);
    setResendMessage(null);
    setLoading(true);
    try {
      await login(email, password);
    } catch (err) {
      if (err instanceof ApiError && err.detail && typeof err.detail === "object" && (err.detail as { code?: unknown }).code === "email_not_verified") {
        setNeedsVerification(true);
        setError("Please verify your email before signing in.");
      } else {
        setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
      }
    } finally {
      setLoading(false);
    }

  }

  async function resendVerification() {
    setResending(true);
    setResendMessage(null);
    try {
      await fetch(`${import.meta.env.VITE_API_BASE_URL}/auth/resend-verification`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      setResendMessage("If an account exists for that email, a new verification link has been sent.");
    } catch {
      setResendMessage("We couldn't resend the email. Please try again.");
    } finally {
      setResending(false);
    }
  }

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
          <span style={{ fontSize: "var(--text-sm)", color: "var(--ink-600)" }}>Sign in to your account</span>
        </div>

        <Card padding={28} elevation="md">
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <div>
              <label style={authLabel} htmlFor="login-email">
                Email
              </label>
              <input
                id="login-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="username"
                style={authInputStyle}
              />
            </div>
            <div>
              <label style={authLabel} htmlFor="login-password">
                Password
              </label>
              <PasswordInput
                id="login-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                style={authInputStyle}
              />
            </div>

            {/* Shown only when the session ended on its own, and only
                while the user has not yet hit a fresh error — landing
                back on this screen with no explanation is what made an
                expiry feel like a fault in the system. */}
            {accountDeleted && !error && (
              <div
                role="status"
                style={{
                  background: "var(--surface-bg)",
                  color: "var(--ink-900)",
                  border: "1px solid var(--surface-border)",
                  borderRadius: "var(--radius)",
                  padding: "10px 12px",
                  fontSize: "var(--text-sm)",
                  lineHeight: 1.5,
                }}
              >
                Your account has been deleted. Your details were erased and any open applications were withdrawn.
              </div>
            )}

            {sessionExpired && !accountDeleted && !error && (
              <div
                style={{
                  background: "var(--surface-bg)",
                  color: "var(--ink-900)",
                  border: "1px solid var(--surface-border)",
                  borderRadius: "var(--radius)",
                  padding: "10px 12px",
                  fontSize: "var(--text-sm)",
                  lineHeight: 1.5,
                }}
              >
                Your session ended after a period of inactivity. Sign in again to pick up
                where you left off.
              </div>
            )}

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
            {needsVerification && (
              <div>
                <Button type="button" variant="secondary" onClick={resendVerification} disabled={resending} style={{ width: "100%" }}>
                  {resending ? "Sending..." : "Resend verification email"}
                </Button>
                {resendMessage && <p role="status" style={{ fontSize: "var(--text-sm)", color: "var(--success-text)" }}>{resendMessage}</p>}
              </div>
            )}

            <Button type="submit" variant="primary" disabled={loading} style={{ width: "100%", padding: "12px 20px" }}>
              {loading ? "Signing in..." : "Sign in"}
            </Button>
          </form>
        </Card>

        <p style={{ textAlign: "center", fontSize: "var(--text-sm)", color: "var(--ink-400)", marginTop: 20 }}>
          <a href="/forgot-password" style={{ color: "var(--accent)", textDecoration: "none", fontWeight: 600 }}>
            Forgot your password?
          </a>
        </p>
        <p style={{ textAlign: "center", fontSize: "var(--text-sm)", color: "var(--ink-400)", marginTop: 8 }}>
          New applicant?{" "}
          <a href={next ? `/signup?next=${encodeURIComponent(next)}` : "/signup"} style={{ color: "var(--accent)", textDecoration: "none", fontWeight: 600 }}>
            Create an account
          </a>
        </p>
        <p style={{ textAlign: "center", fontSize: "var(--text-sm)", color: "var(--ink-400)", marginTop: 8 }}>
          <a href="/" style={{ color: "var(--ink-600)", textDecoration: "none" }}>
            &larr; Back to job board
          </a>
          <span aria-hidden="true" style={{ margin: "0 8px" }}>·</span>
          <a href="/help" style={{ color: "var(--ink-600)", textDecoration: "none" }}>
            Help
          </a>
        </p>
      </div>
    </div>
  );
}
