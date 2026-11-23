import {
  NOTIFICATION_KIND_TAG,
  type NotificationItem as Notice,
  type NotificationKind,
  type NotificationSender,
} from "../../../../shared/api/notifications";
import { relativeTime } from "../../model/notifications";
import { Avatar } from "../../../../shared/ui/Avatar";
import { BellIcon, BriefcaseIcon, CalendarIcon, CheckIcon } from "../../../../shared/ui/icons";
import { Tag, type TagTone } from "../../../../shared/ui/Tag";

/**
 * One notification, drawn the same way everywhere it appears: the bell's
 * list, the corner pop-up and the Notifications page. Only the content:
 * each host wraps it in its own control (a menu item, a list option, the
 * pop-up's button), so this never has to know which one it is in.
 *
 * Unread reads as a bolder line and a red dot, never a tinted row.
 */

/** Each kind's colour, on its tag and on ARKIVE's own notices. */
const KIND_TONE: Record<NotificationKind, TagTone> = {
  schedule: "blue",
  decision: "violet",
  application: "teal",
  system: "neutral",
};

const KIND_ICON: Record<NotificationKind, typeof BellIcon> = {
  schedule: CalendarIcon,
  decision: CheckIcon,
  application: BriefcaseIcon,
  system: BellIcon,
};

const MARK_PX = { sm: 32, md: 36, lg: 44 } as const;

/** Who it came from, as a picture: the person's photo or initials, the
 *  ARKIVE mark for the HR Office, or the kind's icon for ARKIVE's own
 *  notices (and the ones sent before senders were recorded). */
export function SenderMark({
  sender,
  kind,
  size = "md",
}: {
  sender: NotificationSender;
  kind: NotificationKind;
  size?: keyof typeof MARK_PX;
}) {
  if (sender.kind === "person") return <Avatar name={sender.name} src={sender.avatar_url} size={MARK_PX[size]} />;
  if (sender.kind === "office") {
    return (
      <span className={`ark-sender-mark ark-sender-mark--${size} ark-sender-mark--office`} aria-hidden="true">
        <img src="/brand/arkive-logo.png" alt="" />
      </span>
    );
  }
  const Icon = KIND_ICON[kind] ?? BellIcon;
  const icon = Math.round(MARK_PX[size] * 0.44);
  return (
    <span className={`ark-sender-mark ark-sender-mark--${size} ark-tone--${KIND_TONE[kind] ?? "neutral"}`} aria-hidden="true">
      <Icon width={icon} height={icon} />
    </span>
  );
}

export function KindTag({ kind }: { kind: NotificationKind }) {
  return <Tag tone={KIND_TONE[kind] ?? "neutral"}>{NOTIFICATION_KIND_TAG[kind] ?? "Notice"}</Tag>;
}

export function NotificationItem({
  item,
  density = "list",
  now,
}: {
  item: Notice;
  /** list: the Notifications page, with the kind's tag and two lines of
   *  message. menu: the bell, one line. toast: the corner pop-up. */
  density?: "list" | "menu" | "toast";
  now?: Date;
}) {
  const unread = !item.read_at;
  return (
    <span className="ark-nitem" data-density={density} data-unread={unread || undefined}>
      <SenderMark sender={item.sender} kind={item.kind} size={density === "menu" ? "sm" : "md"} />
      <span className="ark-nitem__body">
        <span className="ark-nitem__top">
          <span className="ark-nitem__sender">
            {unread && <span className="ark-visually-hidden">Unread. </span>}
            {item.sender.name}
          </span>
          <time className="ark-nitem__time" dateTime={item.created_at}>
            {relativeTime(item.created_at, now)}
          </time>
        </span>
        <span className="ark-nitem__title">{item.title}</span>
        <span className="ark-nitem__preview">{item.message}</span>
        {density === "list" && (
          <span className="ark-nitem__foot">
            <KindTag kind={item.kind} />
            {item.about && <span className="ark-nitem__job">{item.about.job_title}</span>}
          </span>
        )}
      </span>
      {unread && <span className="ark-nitem__dot" aria-hidden="true" />}
    </span>
  );
}
