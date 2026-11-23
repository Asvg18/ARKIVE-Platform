/** How an invitation's link reaches the person: copied by hand, or
 *  emailed. */

import type { Invite } from "../../../../../shared/api/invites";
import { Button } from "../../../../../shared/ui/Button";
import { Tag } from "../../../../../shared/ui/Tag";
import { inputStyle } from "./formStyle";

/** The invitation link, to copy and send by hand. */
export function LinkBox({ link, copied, onCopy }: { link: string; copied: boolean; onCopy: () => void }) {
  return (
    <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
      <input
        readOnly
        value={link}
        aria-label="Invitation link"
        onFocus={(e) => e.target.select()}
        style={{ ...inputStyle, background: "var(--surface)", fontFamily: "monospace", fontSize: "var(--text-xs)" }}
      />
      <Button variant="secondary" onClick={onCopy} style={{ flexShrink: 0 }}>
        {copied ? "Copied!" : "Copy Link"}
      </Button>
    </div>
  );
}

/** Whether an invitation's link went out by email. Only worth saying
 *  while the invitation is still open; once it was accepted or revoked,
 *  how it travelled no longer matters. */
export function EmailedCell({ invite }: { invite: Invite }) {
  if (invite.status === "accepted" || invite.status === "revoked") {
    return <span style={{ color: "var(--ink-400)" }}>–</span>;
  }
  if (!invite.emailed_at) {
    return (
      <Tag tone="amber" dot title="The link was only shown on screen. Use Resend to email it.">
        Not emailed
      </Tag>
    );
  }
  const sent = new Date(invite.emailed_at);
  return (
    <span title={sent.toLocaleString()}>
      Sent {sent.toLocaleDateString(undefined, { month: "short", day: "numeric" })},{" "}
      {sent.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
    </span>
  );
}
