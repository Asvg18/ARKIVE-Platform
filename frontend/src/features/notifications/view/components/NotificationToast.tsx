import { useEffect, useRef, useState } from "react";
import type { NotificationItem as Notice } from "../../../../shared/api/notifications";
import { BellIcon, XIcon } from "../../../../shared/ui/icons";
import { NotificationItem } from "./NotificationItem";

/**
 * A new notification, shown for a few seconds in the bottom-right corner
 * without being distracting. One at a time, no sound, and it waits
 * while the pointer or keyboard focus is on it, so nobody loses it
 * mid-read. The bell decides when one appears; this only shows it.
 *
 * It is the same item as the bell's
 * list and the Notifications page: who it came from, with their photo,
 * the subject and the message. Several at once read as a count.
 */

const VISIBLE_MS = 6000;
const LEAVE_MS = 260;

export function NotificationToast({
  item,
  count,
  onOpen,
  onClose,
}: {
  /** The one new notice, or null when several arrived together. */
  item: Notice | null;
  count: number;
  onOpen: () => void;
  onClose: () => void;
}) {
  const [leaving, setLeaving] = useState(false);
  const [held, setHeld] = useState(false);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  // a newer notification replaces this one: its time starts afresh
  const key = item ? `n${item.id}` : `c${count}`;

  useEffect(() => {
    if (held || leaving) return;
    const timer = window.setTimeout(() => setLeaving(true), VISIBLE_MS);
    return () => window.clearTimeout(timer);
  }, [held, leaving, key]);

  useEffect(() => {
    if (!leaving) return;
    const timer = window.setTimeout(() => closeRef.current(), LEAVE_MS);
    return () => window.clearTimeout(timer);
  }, [leaving]);

  useEffect(() => setLeaving(false), [key]);

  return (
    <div
      className="ark-toast"
      role="status"
      aria-live="polite"
      data-leaving={leaving || undefined}
      onMouseEnter={() => setHeld(true)}
      onMouseLeave={() => setHeld(false)}
      onFocus={() => setHeld(true)}
      onBlur={() => setHeld(false)}
    >
      <button type="button" className="ark-toast__body" onClick={onOpen}>
        {item ? (
          <NotificationItem item={item} density="toast" />
        ) : (
          <span className="ark-toast__many">
            <span className="ark-sender-mark ark-sender-mark--md ark-tone--neutral" aria-hidden="true">
              <BellIcon width={16} height={16} />
            </span>
            <span>
              <span className="ark-toast__many-title">{count} new notifications</span>
              <span className="ark-toast__many-sub">Open your notifications to see them.</span>
            </span>
          </span>
        )}
      </button>
      <button type="button" className="ark-toast__close" aria-label="Dismiss" onClick={() => setLeaving(true)}>
        <XIcon width={14} height={14} />
      </button>
    </div>
  );
}
