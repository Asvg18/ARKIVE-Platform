/** The badges on the staff and invitation tables: access level, an
 *  invitation's status, and whether an account can sign in. */

import { ACCESS_LABEL, type Invite, type StaffAccess } from "../../../../../shared/api/invites";
import { Tag, type TagTone } from "../../../../../shared/ui/Tag";

/** Only Super Admin takes a colour: it is the one access level worth
 *  spotting at a glance, because it is the one that can change everyone
 *  else's. Violet, not the brand red, which marks the item you selected. */
export function AccessBadge({ access }: { access: StaffAccess }) {
  return <Tag tone={access === "super_admin" ? "violet" : "neutral"}>{ACCESS_LABEL[access]}</Tag>;
}

/** An invitation's link, in the shared status colours: waiting blue,
 *  used green, lapsed neutral, withdrawn by HR amber. */
const INVITE_STATUS: Record<Invite["status"], { tone: TagTone; label: string }> = {
  pending: { tone: "blue", label: "Pending" },
  accepted: { tone: "green", label: "Accepted" },
  expired: { tone: "neutral", label: "Expired" },
  revoked: { tone: "amber", label: "Revoked" },
};

export function StatusBadge({ status }: { status: Invite["status"] }) {
  const { tone, label } = INVITE_STATUS[status];
  return (
    <Tag tone={tone} dot>
      {label}
    </Tag>
  );
}

/** Whether a staff account can currently sign in. Distinct from the
 *  invite StatusBadge above -- that one is about a link's lifecycle, this
 *  is about a person's access. */
export function ActiveBadge({ active }: { active: boolean }) {
  return (
    <Tag tone={active ? "green" : "amber"} dot>
      {active ? "Active" : "Deactivated"}
    </Tag>
  );
}
