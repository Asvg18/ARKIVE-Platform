import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { ApiError, apiFetch } from "../../../../shared/api/client";
import type { ApplicationDetail } from "../../../../shared/api/applicant";
import { Alert } from "../../../../shared/ui/Alert";
import { Button } from "../../../../shared/ui/Button";
import { Modal } from "../../../../shared/ui/Modal";
import { PasswordInput } from "../../../../shared/ui/PasswordInput";

/** The word typed on the last step. The server checks it too. */
const CONFIRM_WORD = "DELETE";

const ACKNOWLEDGEMENTS = [
  "My open applications will be withdrawn, and HR will stop considering me for them.",
  "My resume, documents and letter of intent will be permanently deleted.",
  "This can't be undone. Nobody, including HR, can bring my account back.",
];

type Step = "consequences" | "acknowledge" | "confirm";

/** Deleting an applicant's own account, behind three
 *  warnings rather than one click:
 *    1. what happens — including the named applications that will be
 *       withdrawn, fetched fresh, so nobody learns it afterwards;
 *    2. three things to tick, one per consequence;
 *    3. the password and the word DELETE typed out.
 *  The rule is "erase the person, keep the record": see the backend's
 *  services/account_erasure for exactly what goes and what stays.
 *
 *  On success the session is already dead server-side (the account is
 *  switched off), so this signs out here and lands on the sign-in page
 *  with a note saying it's done. */
export function DeleteAccountDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { token, logout } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("consequences");
  const [openApplications, setOpenApplications] = useState<ApplicationDetail[] | null>(null);
  const [ticked, setTicked] = useState<boolean[]>(ACKNOWLEDGEMENTS.map(() => false));
  const [password, setPassword] = useState("");
  const [confirmText, setConfirmText] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Every opening starts from the first warning, with nothing pre-ticked.
  useEffect(() => {
    if (!open) return;
    setStep("consequences");
    setTicked(ACKNOWLEDGEMENTS.map(() => false));
    setPassword("");
    setConfirmText("");
    setError(null);
    setOpenApplications(null);
    apiFetch<ApplicationDetail[]>("/applicant/applications", { token })
      .then((apps) => setOpenApplications(apps.filter((a) => a.status === "active" || a.status === "flagged")))
      .catch(() => setOpenApplications([]));
  }, [open, token]);

  const allTicked = ticked.every(Boolean);
  const confirmed = confirmText.trim() === CONFIRM_WORD && password.length > 0;

  async function deleteAccount(e?: FormEvent) {
    e?.preventDefault();
    if (!confirmed) return;
    setDeleting(true);
    setError(null);
    try {
      await apiFetch("/account/delete", {
        method: "POST",
        token,
        body: { current_password: password, confirm: confirmText.trim() },
      });
      logout();
      navigate("/login?deleted=1", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't delete your account. Try again.");
      setDeleting(false);
    }
  }

  const stepNumber = step === "consequences" ? 1 : step === "acknowledge" ? 2 : 3;

  const footer =
    step === "consequences" ? (
      <>
        <Button variant="ghost" onClick={onClose}>
          Keep my account
        </Button>
        <Button variant="danger" onClick={() => setStep("acknowledge")} disabled={openApplications === null}>
          Continue
        </Button>
      </>
    ) : step === "acknowledge" ? (
      <>
        <Button variant="ghost" onClick={() => setStep("consequences")}>
          Back
        </Button>
        <Button variant="danger" onClick={() => setStep("confirm")} disabled={!allTicked}>
          Continue
        </Button>
      </>
    ) : (
      <>
        <Button variant="ghost" onClick={() => setStep("acknowledge")} disabled={deleting}>
          Back
        </Button>
        <Button variant="danger" onClick={() => deleteAccount()} disabled={!confirmed || deleting}>
          {deleting ? "Deleting…" : "Delete my account"}
        </Button>
      </>
    );

  return (
    <Modal
      open={open}
      title={
        step === "consequences"
          ? "Delete your account?"
          : step === "acknowledge"
            ? "Before you go"
            : "Confirm it's you"
      }
      sub={
        step === "consequences"
          ? "Read what happens first. It can't be undone."
          : step === "acknowledge"
            ? "Tick each one to show you understand."
            : `Enter your password and type ${CONFIRM_WORD} to delete your account.`
      }
      aside={<span className="ark-modal__step">Step {stepNumber} of 3</span>}
      width={560}
      busy={deleting}
      onClose={onClose}
      footer={footer}
    >
      {step === "consequences" && (
        <div className="ark-delete">
          <section className="ark-delete__block">
            <h3>Your open applications</h3>
            {openApplications === null ? (
              <p className="ark-delete__muted">Checking your applications…</p>
            ) : openApplications.length === 0 ? (
              <p className="ark-delete__muted">You have no open applications, so nothing will be withdrawn.</p>
            ) : (
              <>
                <p>
                  {openApplications.length === 1 ? "This application" : `These ${openApplications.length} applications`} will
                  be withdrawn straight away:
                </p>
                <ul className="ark-delete__apps">
                  {openApplications.map((a) => (
                    <li key={a.id}>
                      <strong>{a.job_title}</strong>
                      <span>{a.job_department}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>

          <section className="ark-delete__block">
            <h3>What's erased</h3>
            <ul className="ark-delete__list">
              <li>Your name, email, photo and password, so you won't be able to sign in again.</li>
              <li>Your resumes, extra documents and letter of intent.</li>
              <li>Your notifications.</li>
            </ul>
          </section>

          <section className="ark-delete__block">
            <h3>What HR keeps</h3>
            <p>
              A record that your applications happened (their stages and scores), shown as “Deleted applicant”, not
              under your name. You can sign up again later with the same email, as a new account.
            </p>
          </section>

          <Alert tone="danger" title="This can't be undone." />
        </div>
      )}

      {step === "acknowledge" && (
        <div className="ark-delete__acks">
          {ACKNOWLEDGEMENTS.map((text, i) => (
            <label key={text} className="ark-ack">
              <input
                type="checkbox"
                checked={ticked[i]}
                onChange={(e) => setTicked((prev) => prev.map((v, j) => (j === i ? e.target.checked : v)))}
              />
              <span>{text}</span>
            </label>
          ))}
        </div>
      )}

      {step === "confirm" && (
        <form className="ark-fields" onSubmit={deleteAccount}>
          <div className="ark-field">
            <label className="ark-field__label" htmlFor="delete-password">
              Password
            </label>
            <PasswordInput
              id="delete-password"
              className="ark-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              autoFocus
            />
          </div>
          <div className="ark-field">
            <label className="ark-field__label" htmlFor="delete-confirm">
              Type <strong className="ark-delete__word">{CONFIRM_WORD}</strong> to confirm
            </label>
            <input
              id="delete-confirm"
              className="ark-input"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          {error && <Alert tone="danger" title={error} />}
          {/* Lets Enter submit the form; the visible button is in the footer. */}
          <button type="submit" hidden aria-hidden="true" tabIndex={-1} />
        </form>
      )}
    </Modal>
  );
}
