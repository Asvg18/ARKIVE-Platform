/** The sign-in email card: the new address takes effect only once the
 *  link sent to it is opened, so a typo can never lock anyone out. */
import { useState, type FormEvent } from "react";
import { useAuth } from "../../../../auth/controller/AuthContext";
import type { Account } from "../../../../../shared/api/account";
import { apiFetch } from "../../../../../shared/api/client";
import { Alert } from "../../../../../shared/ui/Alert";
import { Button } from "../../../../../shared/ui/Button";
import { PasswordInput } from "../../../../../shared/ui/PasswordInput";
import { MailIcon } from "../../../../../shared/ui/icons";
import { errorText } from "./accountModel";
import { Panel } from "./Panel";

export function EmailSection({ account }: { account: Account }) {
  const { token, setMe } = useAuth();
  const [newEmail, setNewEmail] = useState("");
  const [password, setPassword] = useState("");
  const [sending, setSending] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function requestChange(e: FormEvent) {
    e.preventDefault();
    setSending(true);
    setError(null);
    try {
      const updated = await apiFetch<Account>("/account/email-change", {
        method: "POST",
        token,
        body: { new_email: newEmail.trim(), current_password: password },
      });
      setMe(updated);
      setNewEmail("");
      setPassword("");
    } catch (err) {
      setError(errorText(err, "Couldn't send the confirmation link. Try again."));
    } finally {
      setSending(false);
    }
  }

  async function cancelChange() {
    setCancelling(true);
    setError(null);
    try {
      setMe(await apiFetch<Account>("/account/email-change", { method: "DELETE", token }));
    } catch (err) {
      setError(errorText(err, "Couldn't cancel the change. Try again."));
    } finally {
      setCancelling(false);
    }
  }

  return (
    <Panel
      id="account-email"
      title="Sign-in email"
      sub="The address you sign in with. Password resets and ARKIVE's emails go here too."
    >
      <div className="ark-settings-current">
        <span className="ark-settings-current__icon" aria-hidden="true">
          <MailIcon width={16} height={16} />
        </span>
        <span className="ark-settings-current__text">
          <small>Current email</small>
          <strong>{account.email}</strong>
        </span>
      </div>

      {account.pending_email && (
        <Alert
          tone="warning"
          title={
            <>
              Waiting for you to confirm <b>{account.pending_email}</b>
            </>
          }
          action={
            <Button variant="outline" onClick={cancelChange} disabled={cancelling}>
              {cancelling ? "Cancelling…" : "Cancel change"}
            </Button>
          }
        >
          <p className="ark-alert__body">
            We sent a link to that address. Open it within 24 hours to finish. Until then you still sign in with{" "}
            {account.email}.
          </p>
        </Alert>
      )}

      <form className="ark-settings__form" onSubmit={requestChange}>
        <div className="ark-fields ark-fields--2">
          <div className="ark-field">
            <label className="ark-field__label" htmlFor="acct-new-email">
              {account.pending_email ? "Use a different address" : "New email"}
            </label>
            <input
              id="acct-new-email"
              className="ark-input"
              type="email"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              autoComplete="email"
              required
            />
          </div>
          <div className="ark-field">
            <label className="ark-field__label" htmlFor="acct-email-password">
              Current password
            </label>
            <PasswordInput
              id="acct-email-password"
              className="ark-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
        </div>

        {error && <Alert tone="danger" title={error} />}

        <div className="ark-settings__foot">
          <Button type="submit" variant="primary" disabled={sending || !newEmail.trim() || !password}>
            {sending ? "Sending…" : "Send confirmation link"}
          </Button>
        </div>
      </form>
    </Panel>
  );
}
