import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ComponentType,
  type KeyboardEvent,
  type ReactNode
} from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import {
  NOTIFICATION_KIND_LABELS,
  NOTIFICATIONS_CHANGED_EVENT,
  type NotificationCounts,
  type NotificationItem as Notice,
  type NotificationKind,
  type NotificationListResponse,
} from "../../../../shared/api/notifications";
import { useLiveRefresh } from "../../../../shared/hooks/useLiveRefresh";
import {
  emptyCopy, groupByDay,
  mergeFresh,
  nextIndex, parseView,
  staysInView,
  viewQuery,
  type InboxView
} from "../../model/notifications";
import { Button } from "../../../../shared/ui/Button";
import { ErrorState } from "../../../../shared/ui/ErrorState";
import {
  ArchiveIcon,
  BellIcon,
  BriefcaseIcon,
  CalendarIcon,
  CheckIcon, InboxIcon,
  InfoIcon,
  MailIcon,
  SearchIcon,
  XIcon
} from "../../../../shared/ui/icons";
import { NotificationItem } from "../components/NotificationItem";
import { PageHeader } from "../../../../shared/ui/PageHeader";
import type { InboxRole } from "./notifications-page/inboxRole";
import { Folder } from "./notifications-page/Folder";
import { PaneMessage, ReadingPane } from "./notifications-page/ReadingPane";

/** The kinds each role actually receives -- the folder list only offers
 *  those, so nobody is shown a folder that can never fill. */
const ROLE_KINDS: Record<InboxRole, NotificationKind[]> = {
  hr: ["schedule", "decision"],
  evaluator: ["schedule"],
  applicant: ["schedule", "decision", "application"],
};

const KIND_ICON: Record<NotificationKind, typeof BellIcon> = {
  schedule: CalendarIcon,
  decision: CheckIcon,
  application: BriefcaseIcon,
  system: InfoIcon,
};

const PAGE_SIZE = 30;

const SEARCH_DELAY_MS = 250;

/** Where the three panes become list-then-notice. Matches the CSS. */
const NARROW = "(max-width: 1099px)";

function isNarrow(): boolean {
  return typeof window !== "undefined" && window.matchMedia(NARROW).matches;
}

/**
 * Every notification a person has had, as an inbox: folders with counts,
 * a searchable list and a reading pane, side by side the way Outlook and
 * Gmail's split view work. Shared by all
 * three portals, each wrapping it in its own shell.
 *
 * The open notice is in the address (`?n=`), and so is the folder
 * (`?f=`), so refreshing or going back keeps your place. Below 1100px it
 * is the list, then the notice on its own with a way back.
 */
export function NotificationsPage({
  shell: Shell,
  role,
}: {
  shell: ComponentType<{ children: ReactNode; wide?: boolean }>;
  role: InboxRole;
}) {
  const { token } = useAuth();
  const kinds = ROLE_KINDS[role];
  const [params, setParams] = useSearchParams();
  const view = parseView(params.get("f"), kinds);
  const openId = Number(params.get("n")) || null;

  const [items, setItems] = useState<Notice[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [counts, setCounts] = useState<NotificationCounts | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  // The open notice when it isn't in the list loaded (opened from a link
  // to an older one, or one in another folder).
  const [fetched, setFetched] = useState<Notice | null>(null);
  const [missing, setMissing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [focusIndex, setFocusIndex] = useState(0);
  const optionRefs = useRef<(HTMLDivElement | null)[]>([]);
  const paneTitleRef = useRef<HTMLHeadingElement>(null);
  const readOnOpen = useRef<number | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(searchInput.trim()), SEARCH_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  function listUrl(beforeId?: number): string {
    const { folder, kind } = viewQuery(view);
    const search = new URLSearchParams({ limit: String(PAGE_SIZE), folder });
    if (kind) search.set("kind", kind);
    if (query) search.set("q", query);
    if (beforeId !== undefined) search.set("before_id", String(beforeId));
    return `/notifications?${search.toString()}`;
  }

  const loadCounts = useCallback(() => {
    apiFetch<NotificationCounts>("/notifications/counts", { token })
      .then(setCounts)
      .catch(() => {});
  }, [token]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiFetch<NotificationListResponse>(listUrl(), { token })
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        setHasMore(res.has_more);
        setFocusIndex(0);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load your notifications.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, view, query, reloadKey]);

  useEffect(() => loadCounts(), [loadCounts]);

  // New notices land at the top while the page is open. The poll asks
  // with this folder, type and search, so one that doesn't match them
  // never appears mid-search.
  function refresh() {
    apiFetch<NotificationListResponse>(listUrl(), { token })
      .then((res) => setItems((prev) => mergeFresh(prev, res.items)))
      .catch(() => {});
    loadCounts();
  }
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;
  useLiveRefresh(refresh, { enabled: !loading && !loadingMore });
  // the bell marks notices read too
  useEffect(() => {
    const onChange = () => refreshRef.current();
    window.addEventListener(NOTIFICATIONS_CHANGED_EVENT, onChange);
    return () => window.removeEventListener(NOTIFICATIONS_CHANGED_EVENT, onChange);
  }, []);

  const current = items.find((i) => i.id === openId) ?? (fetched?.id === openId ? fetched : null);

  useEffect(() => {
    readOnOpen.current = null;
    setActionError(null);
    setMissing(false);
  }, [openId]);

  // The open notice isn't in the list (opened from a link to an older
  // one, or the search or folder has since left it out): fetch just it.
  // Keyed on the list itself, not on loading going true and false, which
  // a fast answer can do between two renders.
  const fetchingId = useRef<number | null>(null);
  useEffect(() => {
    if (openId === null || loading || fetchingId.current === openId) return;
    if (items.some((i) => i.id === openId) || fetched?.id === openId) return;
    fetchingId.current = openId;
    apiFetch<Notice>(`/notifications/${openId}`, { token })
      .then(setFetched)
      .catch(() => setMissing(true))
      .finally(() => {
        fetchingId.current = null;
      });
  }, [openId, loading, items, fetched, token]);

  function announce() {
    window.dispatchEvent(new CustomEvent(NOTIFICATIONS_CHANGED_EVENT));
  }

  function applyChange(updated: Notice) {
    setItems((prev) =>
      staysInView(updated, view) ? prev.map((i) => (i.id === updated.id ? updated : i)) : prev.filter((i) => i.id !== updated.id)
    );
    setFetched((prev) => (prev?.id === updated.id ? updated : prev));
    loadCounts();
    announce();
  }

  // Opening a notice reads it -- once per opening, so "Mark as unread"
  // on the open notice sticks.
  useEffect(() => {
    if (!current || current.read_at || readOnOpen.current === current.id) return;
    readOnOpen.current = current.id;
    apiFetch<Notice>(`/notifications/${current.id}/read`, { method: "POST", token })
      .then(applyChange)
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.id, current?.read_at]);

  async function act(item: Notice, action: "read" | "unread" | "archive" | "unarchive") {
    setBusy(true);
    setActionError(null);
    try {
      const updated = await apiFetch<Notice>(`/notifications/${item.id}/${action}`, { method: "POST", token });
      applyChange(updated);
      if (!staysInView(updated, view)) closeNotice();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "That didn't work. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  function loadMore() {
    const oldest = items[items.length - 1];
    if (!oldest) return;
    setLoadingMore(true);
    apiFetch<NotificationListResponse>(listUrl(oldest.id), { token })
      .then((res) => {
        setItems((prev) => [...prev, ...res.items]);
        setHasMore(res.has_more);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load more notifications."))
      .finally(() => setLoadingMore(false));
  }

  async function markAllRead() {
    await apiFetch("/notifications/read-all", { method: "POST", token }).catch(() => {});
    const now = new Date().toISOString();
    // Under Unread everything just read leaves the list.
    setItems((prev) => (view === "unread" ? [] : prev.map((i) => ({ ...i, read_at: i.read_at ?? now }))));
    loadCounts();
    announce();
  }

  function setView(next: InboxView) {
    const search = new URLSearchParams();
    if (next !== "inbox") search.set("f", next);
    setParams(search);
  }

  function openNotice(item: Notice, index: number) {
    setFocusIndex(index);
    setParams((prev) => {
      const search = new URLSearchParams(prev);
      search.set("n", String(item.id));
      return search;
    });
    // Narrow, the notice replaces the list, so focus goes with it.
    if (isNarrow()) window.requestAnimationFrame(() => paneTitleRef.current?.focus());
  }

  function closeNotice() {
    setParams((prev) => {
      const search = new URLSearchParams(prev);
      search.delete("n");
      return search;
    });
    window.requestAnimationFrame(() => {
      const index = Math.min(focusIndex, optionRefs.current.length - 1);
      optionRefs.current[index]?.focus();
    });
  }

  function onListKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const target = nextIndex(event.key, Math.min(focusIndex, items.length - 1), items.length);
    if (target !== null) {
      event.preventDefault();
      setFocusIndex(target);
      optionRefs.current[target]?.focus();
    } else if ((event.key === "Enter" || event.key === " ") && items[focusIndex]) {
      event.preventDefault();
      openNotice(items[focusIndex], focusIndex);
    }
  }

  const inboxUnread = counts?.inbox.unread ?? 0;
  // the one option in the tab order, kept on the list as it shrinks
  const tabbable = Math.min(focusIndex, items.length - 1);
  const groups = groupByDay(items);
  const empty = emptyCopy(view, query);
  optionRefs.current.length = items.length;
  let flatIndex = -1;

  return (
    <Shell wide>
      <PageHeader
        title="Notifications"
        description={inboxUnread > 0 ? `${inboxUnread} unread` : "You're all caught up"}
        info={{
          summary: "Everything ARKIVE has notified you about, newest first.",
          points: [
            "Open a notification to read it here. Opening it marks it read.",
            "Archive one to keep it out of your inbox. It stays in Archived, and searchable.",
            "Use the arrow keys to move through the list and Enter to open.",
            "New ones also pop up briefly in the corner of the screen.",
          ],
        }}
        actions={
          <Button variant="secondary" onClick={markAllRead} disabled={inboxUnread === 0}>
            Mark all as read
          </Button>
        }
      />

      <div className="ark-inbox" data-open={openId !== null || undefined}>
        <nav className="ark-inbox__folders" aria-label="Folders">
          <Folder icon={InboxIcon} label="Inbox" count={inboxUnread} active={view === "inbox"} onClick={() => setView("inbox")} />
          <Folder icon={MailIcon} label="Unread" count={inboxUnread} active={view === "unread"} onClick={() => setView("unread")} />
          {kinds.length > 1 && (
            <>
              <span className="ark-inbox__folder-label" aria-hidden="true">Types</span>
              {kinds.map((k) => (
                <Folder
                  key={k}
                  icon={KIND_ICON[k]}
                  label={NOTIFICATION_KIND_LABELS[k]}
                  count={counts?.kinds[k]?.unread ?? 0}
                  active={view === k}
                  onClick={() => setView(k)}
                />
              ))}
            </>
          )}
          <span className="ark-inbox__folder-sep" aria-hidden="true" />
          <Folder
            icon={ArchiveIcon}
            label="Archived"
            count={counts?.archived.total ?? 0}
            quiet
            active={view === "archived"}
            onClick={() => setView("archived")}
          />
        </nav>

        <section className="ark-inbox__list" aria-label="Notifications">
          <div className="ark-inbox__search" role="search">
            <label className="ark-finder__search">
              <SearchIcon width={16} height={16} aria-hidden="true" />
              <span className="ark-visually-hidden">Search notifications</span>
              <input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Search by subject, message or sender"
                maxLength={100}
              />
              {searchInput && (
                <button type="button" className="ark-finder__clear" onClick={() => setSearchInput("")} aria-label="Clear search">
                  <XIcon width={13} height={13} />
                </button>
              )}
            </label>
          </div>

          <div className="ark-inbox__scroll">
            {loading ? (
              <div className="ark-inbox__loading" aria-busy="true" aria-label="Loading notifications">
                {[0, 1, 2, 3, 4].map((i) => (
                  <div key={i} className="ark-skeleton ark-inbox__loading-row" />
                ))}
              </div>
            ) : error && items.length === 0 ? (
              <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />
            ) : items.length === 0 ? (
              <div className="ark-empty">
                <span className="ark-empty__mark" aria-hidden="true">
                  {view === "archived" ? <ArchiveIcon width={20} height={20} /> : <BellIcon width={20} height={20} />}
                </span>
                <span className="ark-empty__title">{empty.title}</span>
                <span className="ark-empty__body">{empty.body}</span>
              </div>
            ) : (
              <>
                <div role="listbox" aria-label="Notifications" className="ark-inbox__options" onKeyDown={onListKeyDown}>
                  {groups.map((group) => (
                    <div key={group.label} role="group" aria-labelledby={`inbox-group-${group.label}`}>
                      <div id={`inbox-group-${group.label}`} className="ark-inbox__group" role="presentation">
                        {group.label}
                      </div>
                      {group.items.map((item) => {
                        flatIndex += 1;
                        const index = flatIndex;
                        return (
                          <div
                            key={item.id}
                            ref={(el) => {
                              optionRefs.current[index] = el;
                            }}
                            role="option"
                            aria-selected={item.id === openId}
                            tabIndex={index === tabbable ? 0 : -1}
                            className="ark-inbox__option"
                            onFocus={() => setFocusIndex(index)}
                            onClick={() => openNotice(item, index)}
                          >
                            <NotificationItem item={item} density="list" />
                          </div>
                        );
                      })}
                    </div>
                  ))}
                </div>
                {hasMore && (
                  <div className="ark-inbox__more">
                    <Button variant="secondary" size="sm" onClick={loadMore} disabled={loadingMore}>
                      {loadingMore ? "Loading…" : "Load more"}
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>
        </section>

        <section className="ark-inbox__pane" aria-label="Notification">
          {current ? (
            <ReadingPane
              item={current}
              role={role}
              busy={busy}
              error={actionError}
              titleRef={paneTitleRef}
              onBack={closeNotice}
              onAct={(action) => act(current, action)}
            />
          ) : openId !== null && missing ? (
            <PaneMessage onBack={closeNotice} title="This notification isn't here" body="It may belong to another account, or the link is out of date." />
          ) : openId !== null ? (
            <div className="ark-inbox__pane-loading" aria-busy="true" aria-label="Loading notification">
              <div className="ark-skeleton ark-inbox__pane-skeleton" />
            </div>
          ) : (
            <div className="ark-inbox__pane-idle">
              <span className="ark-empty__mark" aria-hidden="true">
                <InboxIcon width={20} height={20} />
              </span>
              <span className="ark-empty__title">Select a notification to read it</span>
            </div>
          )}
        </section>
      </div>
    </Shell>
  );
}
