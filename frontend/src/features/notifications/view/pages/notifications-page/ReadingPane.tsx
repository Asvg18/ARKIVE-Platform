/** The reading pane: the open notice in full, what it is about, its
 *  action, and on narrow screens the way back to the list. */

import type { RefObject } from "react";
import { Link } from "react-router-dom";
import { type NotificationItem as Notice } from "../../../../../shared/api/notifications";
import { identityColor, initials } from "../../../../../shared/lib/identity";
import { fullTime, openActionFor } from "../../../model/notifications";
import { Avatar } from "../../../../../shared/ui/Avatar";
import { Button } from "../../../../../shared/ui/Button";
import { IdentityMark } from "../../../../../shared/ui/IdentityMark";
import { ArchiveIcon, ChevronLeftIcon, InfoIcon, MailIcon } from "../../../../../shared/ui/icons";
import { KindTag, SenderMark } from "../../components/NotificationItem";
import type { InboxRole } from "./inboxRole";

function BackButton({ onBack }: { onBack: () => void }) {
  return (
    <button type="button" className="ark-inbox__back" onClick={onBack}>
      <ChevronLeftIcon width={16} height={16} aria-hidden="true" />
      All notifications
    </button>
  );
}

export function PaneMessage({ title, body, onBack }: { title: string; body: string; onBack: () => void }) {
  return (
    <div className="ark-inbox__doc">
      <BackButton onBack={onBack} />
      <div className="ark-empty">
        <span className="ark-empty__title">{title}</span>
        <span className="ark-empty__body">{body}</span>
      </div>
    </div>
  );
}

export function ReadingPane({
  item,
  role,
  busy,
  error,
  titleRef,
  onBack,
  onAct,
}: {
  item: Notice;
  role: InboxRole;
  busy: boolean;
  error: string | null;
  titleRef: RefObject<HTMLHeadingElement | null>;
  onBack: () => void;
  onAct: (action: "read" | "unread" | "archive" | "unarchive") => void;
}) {
  const action = item.available ? openActionFor(item.link) : null;
  const senderNote = item.sender.kind === "system" ? "Sent automatically" : item.sender.role;

  return (
    <article className="ark-inbox__doc" aria-labelledby="inbox-doc-title">
      <BackButton onBack={onBack} />
      <header className="ark-inbox__doc-head">
        <div className="ark-inbox__doc-meta">
          <KindTag kind={item.kind} />
          <time dateTime={item.created_at}>{fullTime(item.created_at)}</time>
        </div>
        <h2 id="inbox-doc-title" ref={titleRef} tabIndex={-1} className="ark-inbox__doc-title">
          {item.title}
        </h2>
        <div className="ark-inbox__from">
          <SenderMark sender={item.sender} kind={item.kind} size="lg" />
          <span className="ark-inbox__from-text">
            <span className="ark-inbox__from-name">{item.sender.name}</span>
            {senderNote && <span className="ark-inbox__from-role">{senderNote}</span>}
          </span>
        </div>
      </header>

      <p className="ark-inbox__message">{item.message}</p>

      {item.about && <AboutCard about={item.about} role={role} />}
      {!item.available && (
        <p className="ark-inbox__gone" role="note">
          <InfoIcon width={15} height={15} aria-hidden="true" />
          What this notification was about is no longer available.
        </p>
      )}

      {error && (
        <p className="ark-inbox__error" role="alert">
          {error}
        </p>
      )}

      <footer className="ark-inbox__actions">
        {action && (
          <Link to={action.href} className="ark-btn ark-btn--primary">
            {action.label}
          </Link>
        )}
        <Button variant="secondary" disabled={busy} onClick={() => onAct(item.read_at ? "unread" : "read")}>
          <MailIcon width={15} height={15} aria-hidden="true" />
          {item.read_at ? "Mark as unread" : "Mark as read"}
        </Button>
        <Button variant="ghost" disabled={busy} onClick={() => onAct(item.archived_at ? "unarchive" : "archive")}>
          <ArchiveIcon width={15} height={15} aria-hidden="true" />
          {item.archived_at ? "Move to inbox" : "Archive"}
        </Button>
      </footer>
    </article>
  );
}

/** What the notice is about. Staff see the candidate; an applicant, whose
 *  own application it is, sees the job. */
function AboutCard({ about, role }: { about: NonNullable<Notice["about"]>; role: InboxRole }) {
  const yours = role === "applicant";
  return (
    <section className="ark-inbox__about" aria-label="About">
      <span className="ark-inbox__about-label">{yours ? "Your application" : "About"}</span>
      <div className="ark-inbox__about-row">
        {yours ? (
          <IdentityMark initials={initials(about.department)} color={identityColor(about.department)} size="lg" />
        ) : (
          <Avatar name={about.candidate_name} src={about.candidate_avatar_url} size={40} />
        )}
        <span className="ark-inbox__about-text">
          <span className="ark-inbox__about-name">{yours ? about.job_title : about.candidate_name}</span>
          <span className="ark-inbox__about-sub">{yours ? about.department : `${about.job_title} · ${about.department}`}</span>
        </span>
      </div>
    </section>
  );
}
