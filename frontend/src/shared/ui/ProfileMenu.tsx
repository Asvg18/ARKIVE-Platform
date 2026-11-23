import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Avatar } from "./Avatar";
import { ChevronDownIcon, LogOutIcon, UserIcon } from "./icons";

/** The signed-in account in the top bar — avatar, name, and the email
 * they sign in with — opening a small anchored dropdown with the account
 * actions. Shared by all three portal shells, which need identical
 * open/close/click-outside behaviour and differ only in the role they
 * pass. The role is in the menu, not under the name: the email is what
 * tells two accounts apart, while the role is already
 * written across the sidebar ("University HR", "Evaluator").
 * Styled by .ark-account and .ark-menu in components.css.
 *
 * The password is changed on Account settings, beside the name, photo
 * and sign-in email. */
export function ProfileMenu({
  name,
  email,
  role,
  avatarUrl,
  settingsHref,
  onLogout,
}: {
  name: string;
  /** Null until /auth/me answers; the role stands in until then. */
  email?: string | null;
  role: string;
  avatarUrl?: string | null;
  /** This portal's Account Settings page. */
  settingsHref: string;
  onLogout: () => void;
}) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={containerRef} style={{ position: "relative" }}>
      <button
        type="button"
        className="ark-account"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu for ${name}`}
      >
        <span className="ark-account__avatar">
          <Avatar name={name} size={36} src={avatarUrl} />
        </span>
        <span className="ark-account__text">
          <span className="ark-account__name">{name}</span>
          <span className="ark-account__email">{email || role}</span>
        </span>
        <ChevronDownIcon width={16} height={16} className="ark-account__caret" aria-hidden="true" />
      </button>

      {open && (
        <div role="menu" className="ark-menu">
          {/* Who is signed in, restated at the top of the menu that signs
              them out — the trigger's name can be cut off, this cannot. */}
          <div className="ark-menu__head">
            <Avatar name={name} size={36} src={avatarUrl} />
            <span className="ark-account__text">
              <span className="ark-account__name">{name}</span>
              {email && <span className="ark-account__email">{email}</span>}
              <span className="ark-account__role">{role}</span>
            </span>
          </div>
          <button
            type="button"
            role="menuitem"
            className="ark-menu__item"
            onClick={() => {
              setOpen(false);
              navigate(settingsHref);
            }}
          >
            <UserIcon width={15} height={15} />
            Account settings
          </button>
          <button
            type="button"
            role="menuitem"
            className="ark-menu__item"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
          >
            <LogOutIcon width={15} height={15} />
            Log out
          </button>
        </div>
      )}

    </div>
  );
}
