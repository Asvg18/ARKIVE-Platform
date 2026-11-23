import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, apiFetch } from "../../../../shared/api/client";
import { Card } from "../../../../shared/ui/Card";
import { Button } from "../../../../shared/ui/Button";
import { Logo } from "../../../../shared/ui/Logo";

type LinkState = "checking" | "valid" | "expired" | "used" | "unknown";

const DEAD_LINK_MESSAGE: Record<Exclude<LinkState, "checking" | "valid">, string> = {
  expired: "This verification link has expired. Links last 24 hours.",
  used: "This link has already been used, or a newer one replaced it.",
  unknown: "This verification link is not valid. It may have been mistyped.",
};

export function VerifyEmailPage() {
  const { token } = useParams<{ token: string }>();
  const [linkState, setLinkState] = useState<LinkState>("checking");
  const [verifying, setVerifying] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setLinkState("unknown");
      return;
    }
    apiFetch<{ status: LinkState }>(`/auth/verify-email/${token}`)
      .then((result) => setLinkState(result.status))
      .catch(() => setLinkState("unknown"));
  }, [token]);

  async function verify() {
    if (!token) return;
    setVerifying(true);
    setError(null);
    try {
      await apiFetch(`/auth/verify-email/${token}`, { method: "POST" });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setVerifying(false);
    }
  }

  return (
    <div className="ark-auth">
      <div className="ark-auth__panel">
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, marginBottom: 28 }}>
          <Logo size={46} />
          <span style={{ fontSize: "var(--text-xl)", fontWeight: 800, color: "var(--ink-900)" }}>ARKIVE</span>
          <span style={{ fontSize: "var(--text-sm)", color: "var(--ink-600)" }}>Verify your email</span>
        </div>
        <Card padding={28} elevation="md">
          {linkState === "checking" && <p>Checking your link…</p>}
          {linkState !== "checking" && linkState !== "valid" && !done && (
            <div style={{ fontSize: "var(--text-sm)", lineHeight: 1.6 }}>
              <p style={{ fontWeight: 600 }}>{DEAD_LINK_MESSAGE[linkState]}</p>
              <Link to="/signup" className="ark-btn ark-btn--primary ark-auth__wide">Create an account</Link>
            </div>
          )}
          {linkState === "valid" && !done && (
            <div>
              <p>Click below to verify your email address.</p>
              {error && <p role="alert" style={{ color: "var(--danger-text)" }}>{error}</p>}
              <Button variant="primary" onClick={verify} disabled={verifying} style={{ width: "100%" }}>
                {verifying ? "Verifying..." : "Verify email"}
              </Button>
            </div>
          )}
          {done && (
            <div role="status">
              <p style={{ fontWeight: 600, color: "var(--success-text)" }}>Your email is verified.</p>
              <p>You can now sign in to ARKIVE.</p>
              <Link to="/login" className="ark-btn ark-btn--primary ark-auth__wide">Go to sign in</Link>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
