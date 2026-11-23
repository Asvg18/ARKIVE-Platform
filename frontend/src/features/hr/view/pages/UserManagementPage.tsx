import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import {
  ACCESS_LABEL,
  accessOf,
  type InvitationEmail,
  type Invite,
  type InviteCreated,
  type StaffAccess,
  type StaffMember,
  type WaitingInterview,
} from "../../../../shared/api/invites";
import { AppShell } from "../components/AppShell";
import { Card } from "../../../../shared/ui/Card";
import { Button } from "../../../../shared/ui/Button";
import { Avatar } from "../../../../shared/ui/Avatar";
import { ErrorState } from "../../../../shared/ui/ErrorState";
import { ConfirmDialog } from "../../../../shared/ui/ConfirmDialog";
import { PageHeader } from "../../../../shared/ui/PageHeader";
import { Alert } from "../../../../shared/ui/Alert";
import { EmailedCell, LinkBox } from "./user-management/inviteParts";
import { label, sectionHeading } from "./user-management/formStyle";
import { AccessBadge, ActiveBadge, StatusBadge } from "./user-management/staffBadges";
import { WaitingList } from "./user-management/WaitingList";

/** One line under the Access choice, so picking it is a decision about
 *  what the person can do rather than a guess from a label. */
const ACCESS_HINT: Record<StaffAccess, string> = {
  evaluator: "Sees only the interviews HR assigns them.",
  hr_admin: "Every hiring page. No User Management.",
  super_admin: "Everything an HR admin has, plus this page: inviting, switching accounts off, making super admins.",
};

/** Super admins provision new hr_admin/evaluator accounts here by
 * inviting an email — no password ever changes hands between HR and the
 * invitee. A single-use link is shown once (`justCreated` below, never
 * retrievable again) for HR to send however they like; the invitee opens
 * it and sets their own name + password at /accept-invite/:token.
 *
 * Super admins only: the sidebar hides this page from other
 * HR admins, this page sends them home, and the API refuses them. */
export function UserManagementPage() {
  const { token, user, me } = useAuth();
  const currentUserId = user?.user_id;
  const isSuperAdmin = me?.is_super_admin === true;
  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [mail, setMail] = useState<InvitationEmail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [formOpen, setFormOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [access, setAccess] = useState<StaffAccess>("evaluator");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [justCreated, setJustCreated] = useState<InviteCreated | null>(null);
  const [copied, setCopied] = useState(false);
  /** An emailed invitation keeps its link folded away: the email is the
   *  way it reaches them, the link only a fallback. */
  const [linkShown, setLinkShown] = useState(false);
  const [resendingId, setResendingId] = useState<number | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [deactivating, setDeactivating] = useState<StaffMember | null>(null);
  /** The switch-off confirmation's list of interviews still owed: null
   *  while it's being asked for. */
  const [waiting, setWaiting] = useState<WaitingInterview[] | null>(null);
  const [waitingError, setWaitingError] = useState(false);
  const [promoting, setPromoting] = useState<StaffMember | null>(null);
  const [demoting, setDemoting] = useState<StaffMember | null>(null);
  const [statusWorking, setStatusWorking] = useState(false);

  function load() {
    setLoading(true);
    setError(null);
    Promise.all([
      apiFetch<StaffMember[]>("/hr/staff", { token }),
      apiFetch<Invite[]>("/hr/invites", { token }),
      apiFetch<InvitationEmail>("/hr/invitation-email", { token }),
    ])
      .then(([s, i, m]) => {
        setStaff(s);
        setInvites(i);
        setMail(m);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load."))
      .finally(() => setLoading(false));
  }

  // Waits for the account to say it is a super admin, so an HR admin who
  // isn't one is sent home without a burst of refused requests first.
  useEffect(() => {
    if (isSuperAdmin) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, reloadKey, isSuperAdmin]);

  /** Swaps in the one row an action returned rather than refetching
   *  both tables — a full reload would collapse the just-created invite
   *  link panel. */
  function replaceRow(updated: StaffMember) {
    setStaff((rows) => rows.map((r) => (r.id === updated.id ? updated : r)));
  }

  async function staffAction(member: StaffMember, action: string, done: () => void) {
    setStatusWorking(true);
    setError(null);
    try {
      replaceRow(await apiFetch<StaffMember>(`/hr/staff/${member.id}/${action}`, { method: "POST", token }));
      done();
    } catch (err) {
      done();
      setError(err instanceof ApiError ? err.message : "Could not update that account.");
    } finally {
      setStatusWorking(false);
    }
  }

  function openDeactivate(member: StaffMember) {
    setDeactivating(member);
    setWaiting(null);
    setWaitingError(false);
    apiFetch<WaitingInterview[]>(`/hr/staff/${member.id}/waiting-interviews`, { token })
      .then(setWaiting)
      .catch(() => {
        setWaiting([]);
        setWaitingError(true);
      });
  }

  async function handleInvite() {
    setSubmitting(true);
    setFormError(null);
    try {
      const created = await apiFetch<InviteCreated>("/hr/invites", {
        method: "POST",
        token,
        body: {
          email: email.trim(),
          role: access === "evaluator" ? "evaluator" : "hr_admin",
          super_admin: access === "super_admin",
        },
      });
      showResult(created);
      setEmail("");
      setAccess("evaluator");
      setFormOpen(false);
      load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not create the invite.");
    } finally {
      setSubmitting(false);
    }
  }

  function showResult(result: InviteCreated) {
    setJustCreated(result);
    setCopied(false);
    setLinkShown(false);
  }

  /** Emails the invitation again with a new link — the old one stops
   *  working. For an email that never arrived, one that couldn't be sent
   *  before email was set up, or a link that ran out. */
  async function handleResend(invite: Invite) {
    setResendingId(invite.id);
    setError(null);
    try {
      const result = await apiFetch<InviteCreated>(`/hr/invites/${invite.id}/resend`, { method: "POST", token });
      showResult(result);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send the invitation again.");
    } finally {
      setResendingId(null);
    }
  }

  async function handleRevoke(inviteId: number) {
    try {
      await apiFetch(`/hr/invites/${inviteId}/revoke`, { method: "POST", token });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not revoke the invite.");
    }
  }

  if (me && !isSuperAdmin) return <Navigate to="/hr" replace />;

  const inviteLink = justCreated ? `${window.location.origin}/accept-invite/${justCreated.token}` : "";

  function copyLink() {
    navigator.clipboard.writeText(inviteLink).then(() => setCopied(true));
  }

  const pendingInvites = invites.filter((i) => i.status === "pending");
  const superAdminCount = staff.filter((s) => s.is_super_admin && s.is_active).length;

  return (
    <AppShell>
      <PageHeader
        title="User Management"
        info={{
          summary: "Invite HR admins and evaluators. They set their own password when they accept.",
          points: [
            "Only super admins see this page. HR admins keep every hiring page without it.",
            "Keep at least two super admins, so one person being away can't lock HR out.",
            "Add specific evaluators to a job's pool from its Workflow Builder page.",
          ],
        }}
        actions={
          <Button variant="primary" onClick={() => setFormOpen((o) => !o)}>
            {formOpen ? "Cancel" : "Invite Staff"}
          </Button>
        }
      />

      {/* Said before anyone invites somebody, not after: without it the
          only sign that email is off was a link where an email should
          have been. */}
      {mail && !mail.configured && (
        <div style={{ marginBottom: 20 }}>
          <Alert tone="warning" title="Invitations can't be emailed from this copy of ARKIVE">
            <p className="ark-field__hint" style={{ color: "var(--ink-700)" }}>
              Its email isn't set up, so each invitation gives you a link to send the person yourself. Whoever runs
              ARKIVE can switch email on in its settings (the SMTP lines in <code>.env</code>) and restart it, then
              use Resend below to email the ones already made.
            </p>
          </Alert>
        </div>
      )}

      {justCreated && (
        <div style={{ marginBottom: 24 }}>
          {justCreated.emailed ? (
            <Alert
              tone="success"
              title={`Invitation emailed to ${justCreated.email}`}
              action={
                <span style={{ display: "inline-flex", gap: 8 }}>
                  <Button variant="ghost" size="sm" onClick={() => setLinkShown((shown) => !shown)}>
                    {linkShown ? "Hide the link" : "Copy the link instead"}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setJustCreated(null)}>
                    Dismiss
                  </Button>
                </span>
              }
            >
              <p className="ark-field__hint" style={{ color: "var(--ink-700)" }}>
                {ACCESS_LABEL[accessOf(justCreated.role, justCreated.super_admin)]} access.{" "}
                {mail?.sender ? `The email comes from ${mail.sender} and has` : "The email has"} a link to set their
                own password, which works once and expires in 7 days. If they can't find it, ask them to check spam.
              </p>
              {linkShown && <LinkBox link={inviteLink} copied={copied} onCopy={copyLink} />}
            </Alert>
          ) : (
            <Alert
              tone="warning"
              title={`Couldn't email ${justCreated.email}: send them this link yourself`}
              action={
                <span style={{ display: "inline-flex", gap: 8 }}>
                  {mail?.configured && (
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={resendingId === justCreated.id}
                      onClick={() => handleResend(justCreated)}
                    >
                      {resendingId === justCreated.id ? "Sending…" : "Try emailing again"}
                    </Button>
                  )}
                  <Button variant="ghost" size="sm" onClick={() => setJustCreated(null)}>
                    Dismiss
                  </Button>
                </span>
              }
            >
              <p className="ark-field__hint" style={{ color: "var(--ink-700)" }}>
                {mail?.configured
                  ? "The mail server didn't accept it."
                  : "Email isn't set up on this copy of ARKIVE."}{" "}
                The link is shown only this once; it works once and expires in 7 days.
              </p>
              <LinkBox link={inviteLink} copied={copied} onCopy={copyLink} />
            </Alert>
          )}
        </div>
      )}

      {formOpen && (
        <Card padding={20} elevation="sm" style={{ marginBottom: 24 }}>
          {/* ark-field keeps each column's rows at their natural height, so
              the Email box stays level with Access when Access's hint wraps
              (Super Admin's runs to two lines). */}
          <div className="ark-fields ark-fields--2">
            <div className="ark-field">
              <label style={label} htmlFor="invite-email">Email</label>
              <input
                id="invite-email"
                type="email"
                className="ark-input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="e.g. devon.cruz@mseuf.edu.ph"
              />
            </div>
            <div className="ark-field">
              <label style={label} htmlFor="invite-access">Access</label>
              <select
                id="invite-access"
                className="ark-input"
                value={access}
                onChange={(e) => setAccess(e.target.value as StaffAccess)}
              >
                <option value="evaluator">{ACCESS_LABEL.evaluator}</option>
                <option value="hr_admin">{ACCESS_LABEL.hr_admin}</option>
                <option value="super_admin">{ACCESS_LABEL.super_admin}</option>
              </select>
              <p className="ark-field__hint">{ACCESS_HINT[access]}</p>
            </div>
          </div>
          {formError && <p style={{ color: "crimson", fontSize: "var(--text-sm)", marginTop: 12 }}>{formError}</p>}
          <Button
            variant="primary"
            style={{ marginTop: 16 }}
            disabled={submitting || !email.trim()}
            onClick={handleInvite}
          >
            {submitting ? "Sending invite..." : "Send Invite"}
          </Button>
        </Card>
      )}

      {(loading || !me) && <p style={{ fontFamily: "var(--arkive-font)", color: "var(--ink-600)" }}>Loading...</p>}
      {error && <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />}

      {me && !loading && (
        <>
          <h2 style={sectionHeading}>Staff</h2>
          <Card padding={0} elevation="md" style={{ marginTop: 12 }}>
            <div style={{ overflowX: "auto" }}>
              <table className="ark-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Access</th>
                    <th>Joined</th>
                    <th className="ark-status-cell ark-status-cell--short">Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {staff.map((s) => {
                    const isSelf = s.id === currentUserId;
                    return (
                      <tr key={s.id}>
                        <td>
                          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            <Avatar name={s.full_name} size={26} src={s.avatar_url} />
                            <span style={{ minWidth: 0 }}>
                              <span style={{ display: "block", fontWeight: 600, color: "var(--ink-900)" }}>{s.full_name}</span>
                              {(s.job_title || s.department) && (
                                <span style={{ display: "block", fontSize: "var(--text-xs)", color: "var(--ink-700)" }}>
                                  {[s.job_title, s.department].filter(Boolean).join(" · ")}
                                </span>
                              )}
                            </span>
                          </div>
                        </td>
                        <td>{s.email}</td>
                        <td>
                          <AccessBadge access={accessOf(s.role, s.is_super_admin)} />
                        </td>
                        <td>{new Date(s.created_at).toLocaleDateString()}</td>
                        <td className="ark-status-cell ark-status-cell--short">
                          <ActiveBadge active={s.is_active} />
                        </td>
                        <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                          {/* Absent for your own row: the server refuses
                              both, and a control that always fails is
                              worse than no control. */}
                          {!isSelf && s.role === "hr_admin" && s.is_active && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => (s.is_super_admin ? setDemoting(s) : setPromoting(s))}
                            >
                              {s.is_super_admin ? "Remove super admin" : "Make super admin"}
                            </Button>
                          )}
                          {!isSelf && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => (s.is_active ? openDeactivate(s) : staffAction(s, "reactivate", () => {}))}
                            >
                              {s.is_active ? "Deactivate" : "Reactivate"}
                            </Button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  {staff.length === 0 && (
                    <tr>
                      <td colSpan={6}>
                        No staff accounts yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>
          {superAdminCount === 1 && (
            <p className="ark-field__hint" style={{ marginTop: 8 }}>
              You're the only super admin. Make a second one, so HR isn't locked out if you're away.
            </p>
          )}

          <h2 style={{ ...sectionHeading, marginTop: 32 }}>Pending Invites</h2>
          <Card padding={0} elevation="md" style={{ marginTop: 12, marginBottom: 24 }}>
            <div style={{ overflowX: "auto" }}>
              <table className="ark-table">
                <thead>
                  <tr>
                    <th>Email</th>
                    <th>Access</th>
                    <th>Invited By</th>
                    <th className="ark-status-cell ark-status-cell--short">Status</th>
                    <th>Email</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {invites.map((i) => (
                    <tr key={i.id}>
                      <td>{i.email}</td>
                      <td>
                        <AccessBadge access={accessOf(i.role, i.super_admin)} />
                      </td>
                      <td>{i.invited_by_name}</td>
                      <td className="ark-status-cell ark-status-cell--short">
                        <StatusBadge status={i.status} />
                      </td>
                      <td>
                        <EmailedCell invite={i} />
                      </td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        {(i.status === "pending" || i.status === "expired") && mail?.configured && (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={resendingId === i.id}
                            onClick={() => handleResend(i)}
                          >
                            {resendingId === i.id ? "Sending…" : "Resend"}
                          </Button>
                        )}
                        {i.status === "pending" && (
                          <Button variant="ghost" size="sm" onClick={() => handleRevoke(i.id)}>
                            Revoke
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {invites.length === 0 && (
                    <tr>
                      <td colSpan={6}>
                        No invites yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>
          {pendingInvites.length === 0 && invites.length > 0 && (
            <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xs)", color: "var(--ink-400)", marginTop: -16 }}>
              No invites currently pending.
            </p>
          )}
        </>
      )}
      <ConfirmDialog
        open={deactivating !== null}
        title="Deactivate this account?"
        description={
          deactivating
            ? `${deactivating.full_name} will be signed out and will not be able to sign in again until a super admin reactivates them. Their evaluations and history are kept.`
            : ""
        }
        confirmLabel="Deactivate"
        confirmVariant="danger"
        confirming={statusWorking}
        onConfirm={() => deactivating && staffAction(deactivating, "deactivate", () => setDeactivating(null))}
        onCancel={() => setDeactivating(null)}
      >
        {deactivating?.role === "evaluator" && (
          <WaitingList name={deactivating.full_name} waiting={waiting} failed={waitingError} />
        )}
      </ConfirmDialog>
      <ConfirmDialog
        open={promoting !== null}
        title="Make this HR admin a super admin?"
        description={
          promoting
            ? `${promoting.full_name} will be able to invite staff, deactivate accounts, and make or remove other super admins.`
            : ""
        }
        confirmLabel="Make super admin"
        confirming={statusWorking}
        onConfirm={() => promoting && staffAction(promoting, "grant-super-admin", () => setPromoting(null))}
        onCancel={() => setPromoting(null)}
      />
      <ConfirmDialog
        open={demoting !== null}
        title="Remove super admin?"
        description={
          demoting
            ? `${demoting.full_name} stays an HR admin with every hiring page, but loses User Management.`
            : ""
        }
        confirmLabel="Remove super admin"
        confirmVariant="danger"
        confirming={statusWorking}
        onConfirm={() => demoting && staffAction(demoting, "remove-super-admin", () => setDemoting(null))}
        onCancel={() => setDemoting(null)}
      />
    </AppShell>
  );
}
