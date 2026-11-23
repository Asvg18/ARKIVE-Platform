/** The three kinds of account, named as the server names them. The access
 *  token carries the same value (auth/model/decodeJwt). */
export type AccountRole = "applicant" | "hr_admin" | "evaluator";

/** The signed-in account, as GET /auth/me and every /account write
 *  return it. */
export interface Account {
  id: number;
  email: string;
  full_name: string;
  role: AccountRole;
  /** Relative to the API (render through Avatar); null = initials. */
  avatar_url: string | null;
  /** Staff only. */
  job_title: string | null;
  department: string | null;
  /** An email change waiting on its confirmation link, if any. */
  pending_email: string | null;
  /** ISO timestamps: "Member since" and the password's "Last changed"
   *  on Account Settings. A null password_changed_at = never changed. */
  created_at: string | null;
  password_changed_at: string | null;
  /** HR admins only: may manage accounts (User Management). The HR
   *  sidebar shows that page only when this is true; the API enforces
   *  it either way. */
  is_super_admin: boolean;
}
