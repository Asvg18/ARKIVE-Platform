import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { apiFetch } from "../../../../shared/api/client";
import {
  NOTIFICATIONS_CHANGED_EVENT,
  type NotificationItem as Notice,
  type NotificationListResponse,
} from "../../../../shared/api/notifications";
import { BellIcon } from "../../../../shared/ui/icons";
import { NotificationItem } from "./NotificationItem";
import { NotificationToast } from "./NotificationToast";
import { useLiveRefresh } from "../../../../shared/hooks/useLiveRefresh";

/** Anchored notification dropdown -- copies ProfileMenu's open/close/
 * click-outside/Escape mechanics exactly.
 *
 * Was fetch-on-mount + fetch-on-open only, so the unread badge never
 * appeared until the page reloaded -- with several people on one
 * deployment, notifications only arrived if you already suspected one
 * existed. Now also refreshed by useLiveRefresh; `load` was already
 * silent by construction (no loading flag, errors swallowed), so it
 * needed no separate background variant.
 *
 * It shows the latest few as the same
 * item the Notifications page and the corner pop-up use, with short
 * times ("2h", "Yesterday"), and "See all" for the rest. */
type Toast = { item: Notice; count: 1 } | { item: null; count: number };

/** How many the dropdown shows; the rest are on the Notifications page. */
const BELL_LIMIT = 8;

/** `allHref` is this portal's Notifications page, linked under the
 *  dropdown and from a pop-up that stands
 *  for several notices at once. */
export function NotificationBell({ allHref }: { allHref: string }) {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Notice[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [toast, setToast] = useState<Toast | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  // The newest notice id already accounted for. null until the first
  // load, which only sets it -- so signing in doesn't pop up everything
  // already waiting, only what arrives while the person is here.
  const seenUpTo = useRef<number | null>(null);
  const openRef = useRef(open);
  openRef.current = open;

  function load() {
    apiFetch<NotificationListResponse>(`/notifications?limit=${BELL_LIMIT}`, { token })
      .then((res) => {
        const newest = res.items[0]?.id ?? 0;
        if (seenUpTo.current !== null && !openRef.current) {
          const since = seenUpTo.current;
          const fresh = res.items.filter((item) => item.id > since && !item.read_at);
          if (fresh.length === 1) setToast({ item: fresh[0], count: 1 });
          else if (fresh.length > 1) setToast({ item: null, count: fresh.length });
        }
        seenUpTo.current = Math.max(seenUpTo.current ?? 0, newest);
        setItems(res.items);
        setUnreadCount(res.unread_count);
      })
      .catch(() => {});
  }

  useEffect(() => {
    seenUpTo.current = null;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // The Notifications page reads, archives and un-reads notices without
  // going through the bell; this keeps the badge honest without waiting
  // for the next poll.
  useEffect(() => {
    window.addEventListener(NOTIFICATIONS_CHANGED_EVENT, load);
    return () => window.removeEventListener(NOTIFICATIONS_CHANGED_EVENT, load);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // Paused while the dropdown is open: the list is re-fetched on open
  // anyway, and reordering items under a cursor that is mid-click is a
  // good way to make someone open the wrong notification.
  useLiveRefresh(load, { enabled: !open });

  useEffect(() => {
    if (!open) return;
    load();
    function onPointerDown(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  /** Straight to what it's about when that page exists; otherwise to the
   *  notice itself on the Notifications page, which says why. */
  function openItem(item: Notice) {
    setOpen(false);
    if (item.link && item.available) {
      if (!item.read_at) {
        apiFetch(`/notifications/${item.id}/read`, { method: "POST", token })
          .then(() => window.dispatchEvent(new CustomEvent(NOTIFICATIONS_CHANGED_EVENT)))
          .catch(() => {});
        setItems((prev) => prev.map((i) => (i.id === item.id ? { ...i, read_at: new Date().toISOString() } : i)));
        setUnreadCount((prev) => Math.max(0, prev - 1));
      }
      navigate(item.link);
    } else {
      // the page opens it, which also reads it
      navigate(`${allHref}?n=${item.id}`);
    }
  }

  function openToast(current: Toast) {
    setToast(null);
    if (current.item) openItem(current.item);
    else navigate(allHref);
  }

  async function markAllRead() {
    await apiFetch("/notifications/read-all", { method: "POST", token }).catch(() => {});
    setItems((prev) => prev.map((i) => ({ ...i, read_at: i.read_at ?? new Date().toISOString() })));
    setUnreadCount(0);
    window.dispatchEvent(new CustomEvent(NOTIFICATIONS_CHANGED_EVENT));
  }

  return (
    <div ref={containerRef} className="ark-bell">
      <button
        type="button"
        className="ark-icon-btn"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : "Notifications"}
      >
        <BellIcon width={19} height={19} />
        {/* the badge is too small for "99+"; the page's counts aren't */}
        {unreadCount > 0 && (
          <span className="ark-icon-btn__badge" aria-hidden="true">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div role="menu" aria-label="Notifications" className="ark-menu ark-bell__menu">
          <div className="ark-bell__head">
            <span className="ark-bell__title">Notifications</span>
            {unreadCount > 0 && (
              <button type="button" className="ark-bell__mark-all" onClick={markAllRead}>
                Mark all as read
              </button>
            )}
          </div>

          {items.length === 0 ? (
            <p className="ark-bell__empty">No notifications yet.</p>
          ) : (
            <div className="ark-bell__list">
              {items.map((item) => (
                <button key={item.id} type="button" role="menuitem" className="ark-bell__item" onClick={() => openItem(item)}>
                  <NotificationItem item={item} density="menu" />
                </button>
              ))}
            </div>
          )}
          <Link to={allHref} className="ark-menu__foot" role="menuitem" onClick={() => setOpen(false)}>
            See all notifications
          </Link>
        </div>
      )}

      {toast && (
        <NotificationToast
          item={toast.item}
          count={toast.count}
          onOpen={() => openToast(toast)}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  );
}
