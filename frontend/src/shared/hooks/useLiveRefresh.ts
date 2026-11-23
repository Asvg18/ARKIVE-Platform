import { useEffect, useRef } from "react";

/**
 * Re-fetches a page's data on an interval and whenever the window
 * regains focus, so screens stop going stale while someone's looking.
 *
 * Why: nothing in the app polled or held a socket -- every page fetched
 * once on mount and never again. With three roles on one shared
 * deployment, every handoff ended in someone pressing refresh: the
 * applicant submits, and the HR pipeline open on another laptop shows
 * nothing until manually reloaded.
 *
 * Polling, not WebSockets/SSE, on purpose -- a socket means connection
 * lifecycle, reconnection, proxy config, a new failure class during a
 * live demo, just to move a few small JSON reads a few seconds sooner
 * for a handful of concurrent users. Boring is the right answer here.
 *
 * Two properties callers depend on:
 *
 * - **The refresh must be silent.** Pages hide their content behind a
 *   `loading` flag while fetching, so a poll wired to the normal load
 *   path would blank the screen every few seconds. Callers pass a fetch
 *   that skips the loading flag and swallows its own errors, keeping
 *   the last good data on a transient blip.
 * - **It stops while the user is working.** `enabled: false` pauses it
 *   entirely -- used wherever a form or dialog is open, since
 *   overwriting state under someone mid-typing is worse than stale data.
 */
export function useLiveRefresh(
  refresh: () => void,
  {
    enabled = true,
    intervalMs = 8000,
  }: {
    enabled?: boolean;
    /**
     * `null` means focus-only: refresh on window focus, never on a
     * timer. For pages whose forms live in child components this page
     * can't see -- a background tick there might re-render a screen out
     * from under someone mid-answer, with no `enabled` flag to gate it.
     */
    intervalMs?: number | null;
  } = {}
) {
  // held in a ref because `refresh` is redefined every render, and
  // depending on it directly would tear down and rebuild the interval
  // each time -- it could never actually reach the end of one
  const saved = useRef(refresh);
  useEffect(() => {
    saved.current = refresh;
  });

  useEffect(() => {
    if (!enabled) return;

    // A hidden tab is nobody's screen. Browsers throttle background
    // timers anyway; skipping explicitly means a laptop left open on a
    // buried tab isn't quietly polling for hours.
    const refreshIfVisible = () => {
      if (document.visibilityState === "visible") saved.current();
    };

    const interval = intervalMs === null ? null : setInterval(refreshIfVisible, intervalMs);
    // Focus and visibility give the effect that actually sells it in a
    // demo: switching to the HR laptop shows current data immediately,
    // rather than up to intervalMs of staleness.
    window.addEventListener("focus", refreshIfVisible);
    document.addEventListener("visibilitychange", refreshIfVisible);

    return () => {
      if (interval !== null) clearInterval(interval);
      window.removeEventListener("focus", refreshIfVisible);
      document.removeEventListener("visibilitychange", refreshIfVisible);
    };
  }, [enabled, intervalMs]);
}
