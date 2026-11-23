/** The right-hand rail's cards: password, sign out, and closing the
 *  account (deleting it for applicants, who to ask for staff). */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../../../auth/controller/AuthContext";
import type { Account } from "../../../../../shared/api/account";
import { Button } from "../../../../../shared/ui/Button";
import { ChangePasswordDialog } from "../../components/ChangePasswordDialog";
import { LockIcon, LogOutIcon, TrashIcon } from "../../../../../shared/ui/icons";
import { DeleteAccountDialog } from "../../components/DeleteAccountDialog";
import { Panel } from "./Panel";
import { formatDay } from "./accountModel";

/** The password: when it last changed, and the way to change it.
 *  Changing it already signs out every other device, so there is no
 *  separate "sign out of all other devices". */
export function PasswordSection({ account }: { account: Account }) {
  const [open, setOpen] = useState(false);
  return (
    <Panel id="account-password" title="Password" sub="Changing it signs you out on every other device.">
      <div className="ark-security__head">
        <span className="ark-security__icon" aria-hidden="true">
          <LockIcon width={16} height={16} />
        </span>
        <span className="ark-security__text">
          <strong>
            {account.password_changed_at
              ? `Last changed ${formatDay(account.password_changed_at)}`
              : "Not changed since your account was created"}
          </strong>
          <small>At least 8 characters.</small>
        </span>
      </div>
      <div>
        <Button variant="secondary" size="sm" onClick={() => setOpen(true)}>
          Change password
        </Button>
      </div>
      <ChangePasswordDialog open={open} onClose={() => setOpen(false)} />
    </Panel>
  );
}

/** Signing out from here as well as the account menu: a settings page is
 *  where people also go looking for it. */
export function SignOutSection() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  return (
    <Panel id="account-sign-out" title="Sign out" sub="End your session on this browser.">
      <div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            logout();
            navigate("/login", { replace: true });
          }}
        >
          <LogOutIcon width={14} height={14} aria-hidden="true" />
          Sign out
        </Button>
      </div>
    </Panel>
  );
}

/** An applicant deleting their account. The card only opens the dialog;
 *  the warnings are in DeleteAccountDialog, three steps long. */
export function DeleteAccountSection() {
  const [open, setOpen] = useState(false);
  return (
    <section className="ark-panel" data-tone="danger" aria-labelledby="account-delete">
      <div className="ark-panel__head">
        <div>
          <h2 id="account-delete" className="ark-panel__title">
            Delete account
          </h2>
          <p className="ark-panel__sub ark-settings__sub">
            Withdraws your open applications and permanently erases your details. This can't be undone.
          </p>
        </div>
      </div>
      <div className="ark-panel__body ark-settings__body">
        <div>
          <Button variant="danger" size="sm" onClick={() => setOpen(true)}>
            <TrashIcon width={14} height={14} aria-hidden="true" />
            Delete my account…
          </Button>
        </div>
      </div>
      <DeleteAccountDialog open={open} onClose={() => setOpen(false)} />
    </section>
  );
}

/** Staff can't delete themselves (an HR admin could remove the last
 *  administrator; an evaluator could vanish mid-round), so the card says
 *  who can. */
export function StaffClosingNote({ role }: { role: Account["role"] }) {
  return (
    <Panel id="account-closing" title="Closing your account">
      <p className="ark-settings__note">
        {role === "hr_admin"
          ? "HR accounts are closed by a super admin, from User Management."
          : "Evaluator accounts are closed by a super admin, from User Management. Ask HR if you're leaving."}
      </p>
    </Panel>
  );
}
