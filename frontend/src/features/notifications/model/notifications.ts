/**
 * The rules behind the notifications inbox, the bell and the corner
 * pop-up, kept out of the components so
 * each one is tested once and all three agree. Times are Philippine
 * time, like every other time in ARKIVE.
 */
import {
  NOTIFICATION_KIND_LABELS,
  type NotificationFolder,
  type NotificationItem,
  type NotificationKind,
} from "../../../shared/api/notifications";
import { formatClock, formatDay, todayInPhilippines } from "../../../shared/lib/scheduleTime";

const DAY_MS = 24 * 60 * 60 * 1000;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** The Philippine calendar day of a moment, as YYYY-MM-DD. */
function phDay(at: Date): string {
  return todayInPhilippines(at);
}

function daysBetween(fromDay: string, toDay: string): number {
  const utc = (day: string) => {
    const [y, m, d] = day.split("-").map(Number);
    return Date.UTC(y, m - 1, d);
  };
  return Math.round((utc(toDay) - utc(fromDay)) / DAY_MS);
}

function phClock(at: Date): string {
  const hhmm = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Manila",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(at);
  return formatClock(hhmm);
}

/** How long ago, as short as the bell and the list need it: "Now",
 *  "5m", "2h", "Yesterday", "Mon", "12 Oct", "12 Oct 2025". */
export function relativeTime(iso: string, now: Date = new Date()): string {
  const at = new Date(iso);
  const ago = now.getTime() - at.getTime();
  if (ago < 60 * 1000) return "Now";
  if (ago < 60 * 60 * 1000) return `${Math.floor(ago / (60 * 1000))}m`;
  const day = phDay(at);
  const days = daysBetween(day, phDay(now));
  if (days <= 0) return `${Math.floor(ago / (60 * 60 * 1000))}h`;
  if (days === 1) return "Yesterday";
  const [y, m, d] = day.split("-").map(Number);
  if (days < 7) return WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
  const short = `${d} ${MONTHS[m - 1]}`;
  return y === Number(phDay(now).slice(0, 4)) ? short : `${short} ${y}`;
}

/** The reading pane's full time: "Thu, 15 Oct 2026 · 2:30 PM". */
export function fullTime(iso: string): string {
  const at = new Date(iso);
  return `${formatDay(phDay(at))} · ${phClock(at)}`;
}

/** Today / Yesterday / Earlier, by Philippine day, keeping the list's
 *  newest-first order inside each group. */
export function groupByDay(items: NotificationItem[], now: Date = new Date()) {
  const today = phDay(now);
  const buckets: Record<"Today" | "Yesterday" | "Earlier", NotificationItem[]> = {
    Today: [],
    Yesterday: [],
    Earlier: [],
  };
  for (const item of items) {
    const days = daysBetween(phDay(new Date(item.created_at)), today);
    buckets[days <= 0 ? "Today" : days === 1 ? "Yesterday" : "Earlier"].push(item);
  }
  return (["Today", "Yesterday", "Earlier"] as const)
    .filter((label) => buckets[label].length > 0)
    .map((label) => ({ label, items: buckets[label] }));
}

/** A folder's or the bell's count: nothing for none, "99+" past 99. */
export function countLabel(count: number): string {
  if (count <= 0) return "";
  return count > 99 ? "99+" : String(count);
}

/** The reading pane's main button, named for where the notice leads. */
export function openActionFor(link: string | null): { label: string; href: string } | null {
  if (!link) return null;
  if (link.startsWith("/hr/applications/")) return { label: "Open candidate profile", href: link };
  if (link.startsWith("/applicant/applications/")) return { label: "Open your application", href: link };
  if (link.startsWith("/evaluator/interviews/")) return { label: "Open interview", href: link };
  return { label: "Open", href: link };
}

/** New notices from a poll go on top of the list already loaded, so a
 *  page reached with "Load more" never jumps back to the start. The poll
 *  asks with the same folder, type and search as the list, so a notice
 *  that doesn't match never arrives here at all. */
export function mergeFresh(current: NotificationItem[], polled: NotificationItem[]): NotificationItem[] {
  const newest = current.length ? current[0].id : 0;
  const fresh = polled.filter((item) => item.id > newest);
  return fresh.length ? [...fresh, ...current] : current;
}

/** Where a key press moves focus in the list, or null for a key the
 *  list doesn't handle. Stops at the ends rather than wrapping. */
export function nextIndex(key: string, index: number, length: number): number | null {
  if (length === 0) return null;
  switch (key) {
    case "ArrowDown":
      return Math.min(index + 1, length - 1);
    case "ArrowUp":
      return Math.max(index - 1, 0);
    case "Home":
      return 0;
    case "End":
      return length - 1;
    default:
      return null;
  }
}

/** What the inbox is showing: a folder, or one kind inside the inbox. */
export type InboxView = "inbox" | "unread" | "archived" | NotificationKind;

/** The `?f=` in the page's address, read back. Anything unknown, or a
 *  kind this role never receives, is the inbox. */
export function parseView(raw: string | null, kinds: NotificationKind[]): InboxView {
  if (raw === "unread" || raw === "archived") return raw;
  if (raw && (kinds as string[]).includes(raw)) return raw as NotificationKind;
  return "inbox";
}

/** The list endpoint's folder and kind for a view. */
export function viewQuery(view: InboxView): { folder: NotificationFolder; kind?: NotificationKind } {
  if (view === "inbox" || view === "unread" || view === "archived") return { folder: view };
  return { folder: "inbox", kind: view };
}

/** Whether a notice still belongs in the view it was changed in: one
 *  archived from the inbox leaves it, and so does one moved back out of
 *  the archive. Reading or un-reading it never moves it. */
export function staysInView(item: NotificationItem, view: InboxView): boolean {
  return view === "archived" ? item.archived_at !== null : item.archived_at === null;
}

/** Each folder's own empty message, and one for a search that found
 *  nothing. */
export function emptyCopy(view: InboxView, query: string): { title: string; body: string } {
  if (query) return { title: `Nothing matches "${query}"`, body: "Try another word, or clear the search." };
  switch (view) {
    case "unread":
      return { title: "You're all caught up", body: "Nothing new since you last looked." };
    case "archived":
      return { title: "Nothing archived", body: "Archive a notification to keep it out of your inbox. It stays here, and searchable." };
    case "inbox":
      return { title: "No notifications yet", body: "When something needs your attention, it will show up here." };
    default:
      return {
        title: `No ${NOTIFICATION_KIND_LABELS[view].toLowerCase()} yet`,
        body: "Notifications of this type will show up here.",
      };
  }
}
