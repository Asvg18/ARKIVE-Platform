import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../../controller/AuthContext";
import { roleHomePath } from "../../model/roleHome";
import { ApiError, apiFetch } from "../../../../shared/api/client";
import { Card } from "../../../../shared/ui/Card";
import { Button } from "../../../../shared/ui/Button";
import { Logo } from "../../../../shared/ui/Logo";

type LinkState = "checking" | "valid" | "expired" | "used" | "unknown";

const DEAD_LINK_MESSAGE: Record<Exclude<LinkState, "checking" | "valid">, string> = {
  expired: "This confirmation link has expired. Links last 24 hours.",
  used: "This link has already been used, or a newer one replaced it.",
  unknown: "This confirmation link is not valid. It may have been mistyped.",
};

/** "Change my sign-in email", step two — opened from the new mailbox.
 *
 * Asks for a click rather than confirming on load: some mail systems
 * open every link in a message to scan it, and a change that happened on
 * that visit would happen without the person ever seeing it.
 *
 * Does not sign anyone in. Opening the link proves the new address is
 * theirs, which is all this step is for; the password was checked when
 * the change was asked for. */
export function ConfirmEmailPage() {
  const { token } = useParams<{ token: string }>();
  const { user, refreshMe } = useAuth();

  const [linkState, setLinkState] = useState<LinkState>("checking");
  const [confirming, setConfirming] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setLinkState("unknown");
      return;
    }
    apiFetch<{ status: LinkState }>(`/account/email-change/${token}`)
      .then((res) => setLinkState(res.status))
      .catch(() => setLinkState("unknown"));
  }, [token]);

  async function confirm() {
    if (!token) return;
    setConfirming(true);
    setError(null);
    try {
      await apiFetch<void>(`/account/email-change/${token}`, { method: "POST" });
      setDone(true);
      // Signed in on this browser already: the top bar should show the
      // new address without a reload.
      if (user) void refreshMe();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setConfirming(false);
    }
  }

  const onward = user ? (
    <Link to={roleHomePath(user.role)} className="ark-btn ark-btn--primary ark-auth__wide">
      Back to ARKIVE
    </Link>
  ) : (
    <Link to="/login" className="ark-btn ark-btn--primary ark-auth__wide">
      Go to sign in
    </Link>
  );

  return (
    <div className="ark-auth">
      <div className="ark-auth__panel">
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, marginBottom: 28 }}>
          <Logo size={46} />
          <span style={{ fontSize: "var(--text-xl)", fontWeight: 800, color: "var(--ink-900)", letterSpacing: "-0.3px" }}>
            ARKIVE
          </span>
          <span style={{ fontSize: "var(--text-sm)", color: "var(--ink-600)" }}>Confirm your new sign-in email</span>
        </div>

        <Card padding={28} elevation="md">
          {linkState === "checking" && (
            <p style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--ink-600)" }}>Checking your link…</p>
          )}

          {linkState !== "checking" && linkState !== "valid" && !done && (
            <div style={{ fontSize: "var(--text-sm)", lineHeight: 1.6 }}>
              <p style={{ margin: 0, fontWeight: 600, color: "var(--ink-900)" }}>{DEAD_LINK_MESSAGE[linkState]}</p>
              <p style={{ margin: "10px 0 18px", color: "var(--ink-700)" }}>
                You can ask for a new one from Account Settings once you're signed in.
              </p>
              {onward}
            </div>
          )}

          {linkState === "valid" && !done && (
            <div style={{ fontSize: "var(--text-sm)", lineHeight: 1.6 }}>
              <p style={{ margin: 0, color: "var(--ink-900)" }}>
                Confirm that you want to sign in to ARKIVE with the address this link was sent to.
              </p>
              {error && (
                <p style={{ margin: "12px 0 0", fontWeight: 600, color: "var(--danger-text)" }} role="alert">
                  {error}
                </p>
              )}
              <Button
                variant="primary"
                onClick={confirm}
                disabled={confirming}
                style={{ width: "100%", padding: "12px 20px", marginTop: 18 }}
              >
                {confirming ? "Confirming…" : "Confirm new email"}
              </Button>
            </div>
          )}

          {done && (
            <div style={{ fontSize: "var(--text-sm)", lineHeight: 1.6 }} role="status">
              <p style={{ margin: 0, fontWeight: 600, color: "var(--success-text)" }}>Your sign-in email has been changed.</p>
              <p style={{ margin: "10px 0 18px", color: "var(--ink-700)" }}>Use it the next time you sign in.</p>
              {onward}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
