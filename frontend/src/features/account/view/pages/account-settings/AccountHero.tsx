import type { Account } from "../../../../../shared/api/account";
import { Avatar } from "../../../../../shared/ui/Avatar";
import { CameraIcon } from "../../../../../shared/ui/icons";
import { roleLabel, type PhotoControls } from "./accountModel";

/** Who this account is, on the portals' dark banner: the photo (click
 *  to view it, the camera to change it), name, sign-in email, staff
 *  title, when they joined, and their role. */
export function AccountHero({ account, photo }: { account: Account; photo: PhotoControls }) {
  const title = [account.job_title, account.department].filter(Boolean).join(", ");
  return (
    <section className="ark-app-hero ark-settings-hero" aria-labelledby="account-hero-title">
      <div className="ark-settings-hero__photo">
        {account.avatar_url ? (
          <button type="button" className="ark-settings-hero__avatar" onClick={photo.view} aria-label="View your photo">
            <Avatar name={account.full_name} src={account.avatar_url} size={80} />
          </button>
        ) : (
          <span className="ark-settings-hero__avatar">
            <Avatar name={account.full_name} size={80} />
          </span>
        )}
        <button
          type="button"
          className="ark-settings-hero__camera"
          onClick={photo.choose}
          disabled={photo.busy}
          aria-label={account.avatar_url ? "Change your photo" : "Add a photo"}
          title={account.avatar_url ? "Change photo" : "Add a photo"}
        >
          <CameraIcon width={15} height={15} />
        </button>
      </div>

      <div className="ark-app-hero__text">
        <span className="ark-app-hero__eyebrow">Account settings</span>
        <h1 id="account-hero-title" className="ark-app-hero__title">
          {account.full_name}
        </h1>
        <div className="ark-app-hero__meta">
          <span>{account.email}</span>
          {title && (
            <>
              <span className="ark-app-hero__sep" aria-hidden="true" />
              <strong>{title}</strong>
            </>
          )}
          {account.created_at && (
            <>
              <span className="ark-app-hero__sep" aria-hidden="true" />
              <span>
                Member since{" "}
                {new Date(account.created_at).toLocaleDateString(undefined, { month: "long", year: "numeric" })}
              </span>
            </>
          )}
        </div>
      </div>

      <div className="ark-app-hero__side">
        <span className="ark-app-hero__status">{roleLabel(account)}</span>
      </div>
    </section>
  );
}
