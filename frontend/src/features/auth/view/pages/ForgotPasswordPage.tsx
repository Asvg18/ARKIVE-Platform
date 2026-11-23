import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../../../../shared/api/client";
import { Card } from "../../../../shared/ui/Card";
import { Button } from "../../../../shared/ui/Button";
import { Logo } from "../../../../shared/ui/Logo";
import { authLabel, authInputStyle } from "../styles/authStyles";

/** "I forgot my password", step one.
 *
 * The confirmation deliberately says *if* that address has an account,
 * and shows the same words whatever was typed. The API answers
 * identically for a known and an unknown address on purpose -- anything
 * else would let anyone check who has an account here -- so the screen
 * has to keep that promise rather than undo it. */
export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await apiFetch<void>("/auth/forgot-password", { method: "POST", body: { email } });
      setSent(true);
    } catch (err) {
      // Only a network or server fault can land here -- the endpoint
      // answers 202 for every address it is given.
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
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
          <span style={{ fontSize: "var(--text-sm)", color: "var(--ink-600)" }}>Reset your password</span>
        </div>

        <Card padding={28} elevation="md">
          {sent ? (
            <div style={{ fontSize: "var(--text-sm)", color: "var(--ink-900)", lineHeight: 1.6 }}>
              <p style={{ margin: 0, fontWeight: 600 }}>Check your email.</p>
              <p style={{ margin: "10px 0 0", color: "var(--ink-600)" }}>
                If <strong>{email}</strong> has an ARKIVE account, we&rsquo;ve sent a link for
                choosing a new password. It works once and expires in an hour.
              </p>
              <p style={{ margin: "10px 0 0", color: "var(--ink-600)" }}>
                Nothing arrived? Check the spam folder, or ask HR to confirm the address on your
                account.
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 18 }}>
              <p style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--ink-600)", lineHeight: 1.55 }}>
                Enter the email address on your account and we&rsquo;ll send you a link to choose a
                new password.
              </p>
              <div>
                <label style={authLabel} htmlFor="forgot-email">
                  Email
                </label>
                <input
                  id="forgot-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="username"
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

              <Button type="submit" variant="primary" disabled={loading} style={{ width: "100%", padding: "12px 20px" }}>
                {loading ? "Sending..." : "Send reset link"}
              </Button>
            </form>
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
