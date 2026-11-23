export type StaffRole = "hr_admin" | "evaluator";
export type InviteStatusValue = "pending" | "accepted" | "expired" | "revoked";

export interface Invite {
  id: number;
  email: string;
  role: StaffRole;
  status: InviteStatusValue;
  /** An HR admin invitation that creates a super admin. */
  super_admin: boolean;
  /** "ARKIVE setup" for the first-admin setup step's invitation. */
  invited_by_name: string;
  created_at: string;
  expires_at: string;
  accepted_at: string | null;
  /** When the link last went out by email; null = it never did, and was
   *  only shown on screen to pass on by hand. */
  emailed_at: string | null;
}

export interface InviteCreated extends Invite {
  token: string;
  /** Whether ARKIVE actually sent the invitation by email. False when no
   *  mail server is configured, or when the send failed — the link is
   *  returned either way, so HR can fall back to sending it themselves. */
  emailed: boolean;
}

export interface InviteCreateRequest {
  email: string;
  role: StaffRole;
  super_admin?: boolean;
}

export interface InviteStatus {
  email: string;
  role: StaffRole;
  status: InviteStatusValue;
  super_admin: boolean;
}

/** Whether this copy of ARKIVE can email invitations at all, and the
 *  address they come from. */
export interface InvitationEmail {
  configured: boolean;
  sender: string | null;
}

/** An interview left waiting if its evaluator were switched off. */
export interface WaitingInterview {
  application_id: number;
  candidate_name: string;
  job_title: string;
  stage_label: string;
}

export interface StaffMember {
  id: number;
  full_name: string;
  email: string;
  avatar_url?: string | null;
  /** From their own Account Settings. */
  job_title?: string | null;
  department?: string | null;
  role: StaffRole;
  created_at: string;
  provisioning_source: string;
  /** False once a super admin has switched them off. The account keeps
   *  its history and its password; it simply cannot sign in or act. */
  is_active: boolean;
  is_super_admin: boolean;
}

/** What someone can do, as User Management offers it: the role, plus
 *  whether an HR admin also manages accounts. */
export type StaffAccess = "evaluator" | "hr_admin" | "super_admin";

export const ACCESS_LABEL: Record<StaffAccess, string> = {
  evaluator: "Evaluator",
  hr_admin: "HR Admin",
  super_admin: "Super Admin",
};

export function accessOf(role: StaffRole, superAdmin: boolean): StaffAccess {
  return role === "hr_admin" && superAdmin ? "super_admin" : role;
}
