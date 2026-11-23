/** What a notice is about — backend app.services.notifications.NotificationKind. */
export type NotificationKind = "schedule" | "decision" | "application" | "system";

/** The inbox's folders. A kind narrows the inbox; it is not a folder. */
export type NotificationFolder = "inbox" | "unread" | "archived";

/** Who a notice is shown as coming from, already decided by the server
 *  for whoever is reading: a person (HR and evaluators see who acted),
 *  the HR Office (what applicants see whenever staff acted) or ARKIVE
 *  itself (automatic notices, and ones sent before senders existed). */
export interface NotificationSender {
  kind: "person" | "office" | "system";
  name: string;
  role: string | null;
  avatar_url: string | null;
}

/** The application a notice is about: the reading pane's About card. */
export interface NotificationAbout {
  application_id: number;
  requisition_id: number;
  candidate_name: string;
  candidate_avatar_url: string | null;
  job_title: string;
  department: string;
}

export interface NotificationItem {
  id: number;
  title: string;
  message: string;
  link: string | null;
  kind: NotificationKind;
  read_at: string | null;
  archived_at: string | null;
  created_at: string;
  sender: NotificationSender;
  about: NotificationAbout | null;
  /** False when the page it opens no longer exists (its job was deleted). */
  available: boolean;
}

export interface NotificationListResponse {
  items: NotificationItem[];
  /** Unread notices still in the inbox: the bell's badge. */
  unread_count: number;
  /** Older notices exist past this page (the Notifications page's "Load more"). */
  has_more: boolean;
}

export interface NotificationFolderCount {
  total: number;
  unread: number;
}

/** The inbox's folder list. Kinds count inside the inbox only. */
export interface NotificationCounts {
  inbox: NotificationFolderCount;
  archived: NotificationFolderCount;
  kinds: Record<NotificationKind, NotificationFolderCount>;
}

/** A kind as a folder in the inbox's sidebar. */
export const NOTIFICATION_KIND_LABELS: Record<NotificationKind, string> = {
  schedule: "Schedules",
  decision: "Decisions",
  application: "Application updates",
  system: "Other",
};

/** A kind as the tag on one notice. */
export const NOTIFICATION_KIND_TAG: Record<NotificationKind, string> = {
  schedule: "Schedule",
  decision: "Decision",
  application: "Application",
  system: "Notice",
};

/** Fired after notices are read, archived or marked unread outside the
 *  bell (the Notifications page), so the bell's unread badge catches up
 *  at once instead of on its next poll. */
export const NOTIFICATIONS_CHANGED_EVENT = "arkive:notifications-changed";
