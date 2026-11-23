import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { roleHomePath } from "../../../auth/model/roleHome";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { ApplicationDetail } from "../../../../shared/api/applicant";
import { Avatar } from "../../../../shared/ui/Avatar";
import { Button } from "../../../../shared/ui/Button";
import { PasswordInput } from "../../../../shared/ui/PasswordInput";
import { MiniApplication } from "./landingSections";

const ROLE_LABELS: Record<string, string> = {
  applicant: "an applicant",
  hr_admin: "an HR administrator",
  evaluator: "an interviewer",
};

/**
 * Sign in without leaving the job board.
 *
 * An applicant arriving to check on an application they already
 * submitted should not have to hunt for a Sign In button in the corner.
 * It is the real endpoint, not a decorative form.
 *
 * Deliberately no "continue with Google / Microsoft" buttons: there is no
 * OAuth in this system, and rendering them would put two controls on the
 * front page that cannot work.
 */
export function HeroSignIn() {
  const { user, token, login, me } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // null while unknown, [] once known to be empty — so the panel can stay
  // quiet rather than flashing "you have not applied yet" during the fetch.
  const [myApplications, setMyApplications] = useState<ApplicationDetail[] | null>(null);

  // The JWT carries user_id and role but no name; the name and photo
  // come from the account auth context already holds.
  const fullName = me?.full_name ?? null;
  useEffect(() => {
    if (!user) { setMyApplications(null); return; }
    if (user.role === "applicant") {
      apiFetch<ApplicationDetail[]>("/applicant/applications", { token })
        .then(setMyApplications)
        .catch(() => setMyApplications([]));
    }
  }, [user, token]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in.");
    } finally {
      setBusy(false);
    }
  }

  // Already signed in: answer the question a returning visitor actually
  // has — *where are my applications* — rather than confirming who they are.
  if (user) {
    return (
      <div className="ark-home__signin">
        <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
          <Avatar name={fullName ?? "?"} size={40} src={me?.avatar_url} />
          <div style={{ minWidth: 0 }}>
            <div className="ark-home__signin-name">{fullName ?? "Signed in"}</div>
            <div className="ark-home__signin-role">Signed in as {ROLE_LABELS[user.role] ?? user.role}</div>
          </div>
        </div>

        {user.role === "applicant" && (
          <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid var(--hairline)" }}>
            {myApplications === null ? null : myApplications.length === 0 ? (
              <p style={{ fontSize: "var(--text-sm)", color: "var(--ink-700)", margin: 0, lineHeight: 1.55 }}>
                You have not applied to anything yet. The openings below are a good place to start.
              </p>
            ) : (
              <>
                <div className="ark-home__signin-eyebrow">Your applications</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {myApplications.slice(0, 3).map((a) => (
                    <MiniApplication key={a.id} application={a} />
                  ))}
                </div>
                {myApplications.length > 3 && (
                  <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-700)", marginTop: 10 }}>
                    and {myApplications.length - 3} more
                  </div>
                )}
              </>
            )}
          </div>
        )}

        <Button variant="primary" style={{ width: "100%", marginTop: 18 }} onClick={() => navigate(roleHomePath(user.role))}>
          {user.role === "applicant" ? "Open My Applications" : "Go to My Dashboard"}
        </Button>
      </div>
    );
  }

  return (
    <div className="ark-home__signin">
      <div className="ark-home__signin-eyebrow">Already applied?</div>
      <div className="ark-home__signin-title">Track your application</div>
      <p className="ark-home__signin-lede">Sign in to see which stage you have reached.</p>

      <form onSubmit={submit} className="ark-home__signin-form">
        <label className="ark-field">
          <span className="ark-field__label">Email address</span>
          <input
            className="ark-input"
            type="email"
            value={email}
            required
            autoComplete="email"
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </label>
        {/* A div, not a wrapping label like the email field's: the
            show/hide button can't sit inside a label. */}
        <div className="ark-field">
          <span className="ark-field__label-row">
            <label className="ark-field__label" htmlFor="home-signin-password">
              Password
            </label>
            <a
              href="/forgot-password"
              className="ark-home__forgot"
              onClick={(e) => {
                e.preventDefault();
                navigate("/forgot-password");
              }}
            >
              Forgot?
            </a>
          </span>
          <PasswordInput
            id="home-signin-password"
            className="ark-input"
            value={password}
            required
            autoComplete="current-password"
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
          />
        </div>

        {error && <p className="ark-home__signin-error">{error}</p>}

        <Button type="submit" variant="primary" disabled={busy} style={{ width: "100%" }}>
          {busy ? "Signing in…" : "Sign In"}
        </Button>
      </form>

      <div className="ark-home__signin-foot">
        New applicant?{" "}
        <a
          href="/signup"
          onClick={(e) => {
            e.preventDefault();
            navigate("/signup");
          }}
        >
          Create an account
        </a>
      </div>
    </div>
  );
}
