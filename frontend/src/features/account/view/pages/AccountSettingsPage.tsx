/**
 * Account Settings, one page for every role: the person on the portals'
 * dark banner, the forms on the left, and password, sign-out and closing
 * the account in a rail on the right.
 */

import { useRef, useState, type ChangeEvent, type ComponentType, type ReactNode } from "react";
import { useAuth } from "../../../auth/controller/AuthContext";
import type { Account } from "../../../../shared/api/account";
import { apiFetch } from "../../../../shared/api/client";
import { Button } from "../../../../shared/ui/Button";
import { ConfirmDialog } from "../../../../shared/ui/ConfirmDialog";
import { PhotoViewer } from "../../../../shared/ui/PhotoViewer";
import { CameraIcon } from "../../../../shared/ui/icons";
import { PhotoCropDialog } from "../components/PhotoCropDialog";
import { errorText, roleLabel, type PhotoControls } from "./account-settings/accountModel";
import { AccountHero } from "./account-settings/AccountHero";
import { ProfileSection } from "./account-settings/ProfileSection";
import { EmailSection } from "./account-settings/EmailSection";
import { DeleteAccountSection, PasswordSection, SignOutSection, StaffClosingNote } from "./account-settings/RailSections";

/** The portal's shell comes from the route in App.tsx, as for the
 *  Notifications page, so Account depends on no other feature. `wide`
 *  only changes the applicant shell; HR and evaluator ignore it. */
export function AccountSettingsPage({
  shell: Shell,
}: {
  shell: ComponentType<{ children: ReactNode; wide?: boolean }>;
}) {
  return (
    <Shell wide>
      <AccountSettings />
    </Shell>
  );
}

/** Holds the photo's state for the banner and the Profile card: a picked
 * photo opens PhotoCropDialog to be framed before upload, and the saved
 * one opens in PhotoViewer. Every write returns the updated account,
 * which goes straight into auth context so the top bar changes with it. */
function AccountSettings() {
  const { me, token, setMe } = useAuth();
  const fileInput = useRef<HTMLInputElement>(null);
  const [cropFile, setCropFile] = useState<File | null>(null);
  const [photoSaving, setPhotoSaving] = useState(false);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [removing, setRemoving] = useState(false);

  if (!me) {
    return (
      <div className="ark-settings" aria-busy="true" aria-label="Loading your account">
        <div className="ark-skeleton" style={{ height: 136, borderRadius: "var(--radius-xl)" }} />
        <div className="ark-settings__grid">
          <div className="ark-skeleton" style={{ height: 420, borderRadius: "var(--radius-lg)" }} />
          <div className="ark-skeleton" style={{ height: 360, borderRadius: "var(--radius-lg)" }} />
        </div>
      </div>
    );
  }

  function pickPhoto(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    // Cleared so picking the same file again still opens the framing step.
    e.target.value = "";
    if (!file) return;
    setPhotoError(null);
    setViewerOpen(false);
    setCropFile(file);
  }

  async function uploadPhoto(photo: Blob) {
    setPhotoSaving(true);
    setPhotoError(null);
    try {
      const form = new FormData();
      form.append("file", photo, "photo.jpg");
      setMe(await apiFetch<Account>("/account/avatar", { method: "PUT", token, body: form }));
      setCropFile(null);
    } catch (err) {
      setPhotoError(errorText(err, "Couldn't upload your photo. Try again."));
    } finally {
      setPhotoSaving(false);
    }
  }

  async function removePhoto() {
    setRemoving(true);
    setRemoveError(null);
    try {
      setMe(await apiFetch<Account>("/account/avatar", { method: "DELETE", token }));
      setConfirmRemove(false);
      setViewerOpen(false);
    } catch (err) {
      setRemoveError(errorText(err, "Couldn't remove your photo. Try again."));
      setConfirmRemove(false);
    } finally {
      setRemoving(false);
    }
  }

  const photo: PhotoControls = {
    choose: () => fileInput.current?.click(),
    view: () => setViewerOpen(true),
    remove: () => setConfirmRemove(true),
    busy: photoSaving || removing,
  };

  return (
    <div className="ark-settings">
      <input
        ref={fileInput}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        onChange={pickPhoto}
        hidden
      />

      <AccountHero account={me} photo={photo} />

      <div className="ark-settings__grid">
        <div className="ark-settings__main">
          <ProfileSection account={me} photo={photo} photoError={removeError} />
          <EmailSection account={me} />
        </div>
        <aside className="ark-settings__rail" aria-label="Password and account">
          <PasswordSection account={me} />
          <SignOutSection />
          {me.role === "applicant" ? <DeleteAccountSection /> : <StaffClosingNote role={me.role} />}
        </aside>
      </div>

      <PhotoCropDialog
        file={cropFile}
        saving={photoSaving}
        error={photoError}
        onCancel={() => setCropFile(null)}
        onSave={uploadPhoto}
      />

      <PhotoViewer
        open={viewerOpen && !!me.avatar_url}
        src={me.avatar_url}
        name={me.full_name}
        caption={[me.job_title, me.department].filter(Boolean).join(", ") || roleLabel(me)}
        actions={
          <>
            <Button variant="secondary" size="sm" onClick={photo.choose}>
              <CameraIcon width={14} height={14} aria-hidden="true" />
              Change photo
            </Button>
            <Button variant="ghost" size="sm" className="ark-viewer__ghost" onClick={photo.remove}>
              Remove
            </Button>
          </>
        }
        onClose={() => setViewerOpen(false)}
      />

      <ConfirmDialog
        open={confirmRemove}
        title="Remove your photo?"
        description="You'll show as your initials everywhere in ARKIVE until you add another one."
        confirmLabel="Remove photo"
        cancelLabel="Keep it"
        confirmVariant="danger"
        confirming={removing}
        onConfirm={removePhoto}
        onCancel={() => setConfirmRemove(false)}
      />
    </div>
  );
}
