/** Account Settings' shared wording and shapes: role names, error text,
 *  dates, and the photo's actions. */

import type { Account } from "../../../../../shared/api/account";
import { ApiError } from "../../../../../shared/api/client";

const ROLE_LABEL: Record<Account["role"], string> = {
  hr_admin: "HR Admin",
  evaluator: "Evaluator",
  applicant: "Applicant",
};

/** An HR admin who also manages accounts reads as one, everywhere they
 *  see their own role. */
export function roleLabel(account: Account): string {
  return account.role === "hr_admin" && account.is_super_admin ? "Super Admin" : ROLE_LABEL[account.role];
}

export function errorText(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

export function formatDay(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });
}

/** The photo's actions, shared by the banner and the Profile panel. */
export interface PhotoControls {
  choose: () => void;
  view: () => void;
  remove: () => void;
  busy: boolean;
}
