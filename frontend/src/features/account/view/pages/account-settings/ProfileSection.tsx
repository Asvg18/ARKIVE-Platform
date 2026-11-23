/** The Profile card: photo, display name, and for staff a job title and
 *  department, shown wherever the person appears in ARKIVE. */
import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../../../../auth/controller/AuthContext";
import type { Account } from "../../../../../shared/api/account";
import { apiFetch } from "../../../../../shared/api/client";
import { Alert } from "../../../../../shared/ui/Alert";
import { Avatar } from "../../../../../shared/ui/Avatar";
import { Button } from "../../../../../shared/ui/Button";
import { CameraIcon, CheckIcon, TrashIcon } from "../../../../../shared/ui/icons";
import { errorText, type PhotoControls } from "./accountModel";
import { Panel } from "./Panel";

export function ProfileSection({
  account,
  photo,
  photoError,
}: {
  account: Account;
  photo: PhotoControls;
  photoError: string | null;
}) {
  const { token, setMe } = useAuth();
  const isStaff = account.role !== "applicant";

  const [name, setName] = useState(account.full_name);
  const [jobTitle, setJobTitle] = useState(account.job_title ?? "");
  const [department, setDepartment] = useState(account.department ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dirty =
    name.trim() !== account.full_name ||
    (isStaff && (jobTitle.trim() !== (account.job_title ?? "") || department.trim() !== (account.department ?? "")));

  // Typing again after a save clears the "Saved" mark.
  useEffect(() => {
    if (dirty) setSaved(false);
  }, [dirty]);

  async function saveProfile(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError("Your name can't be empty.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await apiFetch<Account>("/account/profile", {
        method: "PATCH",
        token,
        body: isStaff ? { full_name: name, job_title: jobTitle, department } : { full_name: name },
      });
      setMe(updated);
      setName(updated.full_name);
      setJobTitle(updated.job_title ?? "");
      setDepartment(updated.department ?? "");
      setSaved(true);
    } catch (err) {
      setError(errorText(err, "Couldn't save your profile. Try again."));
    } finally {
      setSaving(false);
    }
  }

  function discard() {
    setName(account.full_name);
    setJobTitle(account.job_title ?? "");
    setDepartment(account.department ?? "");
    setError(null);
  }

  return (
    <Panel
      id="account-profile"
      title="Profile"
      sub={
        isStaff
          ? "How you appear to colleagues and applicants: on interview rounds, evaluator pools and the staff list."
          : "How you appear to the university's HR office on your applications."
      }
    >
      <div className="ark-settings-photo">
        {account.avatar_url ? (
          <button type="button" className="ark-settings-photo__view" onClick={photo.view} aria-label="View your photo">
            <Avatar name={account.full_name} src={account.avatar_url} size={72} />
          </button>
        ) : (
          <span className="ark-settings-photo__view" data-empty>
            <Avatar name={name.trim() || account.full_name} size={72} />
          </span>
        )}
        <div className="ark-settings-photo__text">
          <span className="ark-settings-photo__title">Profile photo</span>
          <span className="ark-settings-photo__hint">
            JPG, PNG or WebP. After choosing one you can drag and zoom to frame it.
          </span>
          <div className="ark-settings-photo__actions">
            <Button variant="secondary" size="sm" onClick={photo.choose} disabled={photo.busy}>
              <CameraIcon width={14} height={14} aria-hidden="true" />
              {account.avatar_url ? "Change photo" : "Upload photo"}
            </Button>
            {account.avatar_url && (
              <>
                <Button variant="ghost" size="sm" onClick={photo.view}>
                  View
                </Button>
                <Button variant="ghost" size="sm" onClick={photo.remove} disabled={photo.busy}>
                  <TrashIcon width={14} height={14} aria-hidden="true" />
                  Remove
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
      {photoError && <Alert tone="danger" title={photoError} />}

      <form className="ark-settings__form" onSubmit={saveProfile}>
        <div className="ark-field">
          <label className="ark-field__label" htmlFor="acct-name">
            Display name
          </label>
          <input
            id="acct-name"
            className="ark-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={255}
            autoComplete="name"
          />
        </div>

        {isStaff && (
          <div className="ark-fields ark-fields--2">
            <div className="ark-field">
              <label className="ark-field__label" htmlFor="acct-title">
                Job title <span className="ark-field__req">Optional</span>
              </label>
              <input
                id="acct-title"
                className="ark-input"
                value={jobTitle}
                onChange={(e) => setJobTitle(e.target.value)}
                maxLength={120}
                placeholder="e.g. Dean"
                autoComplete="organization-title"
              />
            </div>
            <div className="ark-field">
              <label className="ark-field__label" htmlFor="acct-dept">
                Department / office <span className="ark-field__req">Optional</span>
              </label>
              <input
                id="acct-dept"
                className="ark-input"
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                maxLength={120}
                placeholder="e.g. College of Computing"
              />
            </div>
          </div>
        )}

        {error && <Alert tone="danger" title={error} />}

        <div className="ark-settings__foot">
          {saved && !dirty && (
            <span className="ark-field__flag ark-field__flag--ok" role="status">
              <CheckIcon width={13} height={13} aria-hidden="true" />
              Saved
            </span>
          )}
          {dirty && (
            <Button type="button" variant="ghost" onClick={discard} disabled={saving}>
              Discard
            </Button>
          )}
          <Button type="submit" variant="primary" disabled={!dirty || saving}>
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </form>
    </Panel>
  );
}
