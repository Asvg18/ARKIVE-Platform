import { useEffect, useRef, useState } from "react";
import { Button } from "./Button";

/** How long the button stays in its "Retrying..." state at minimum.
 *
 * A dead backend refuses the connection in about a millisecond, so
 * without a floor here the retry finishes before the browser paints a
 * single frame -- the same error re-renders and the button looks broken
 * even though it fired a real request. */
const MIN_FEEDBACK_MS = 600;

/** Renders after a failed data load. onRetry re-runs the same fetch
 * that failed, so a transient blip (backend restart, laptop waking from
 * sleep) is recoverable without a manual page refresh.
 *
 * On success the parent swaps this out for real content. On repeated
 * failure the message stays put, but visibly going through "Retrying..."
 * is what tells the user the attempt happened and genuinely failed
 * again, rather than the click being ignored. */
export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  const [retrying, setRetrying] = useState(false);
  const timerRef = useRef<number | undefined>(undefined);

  // The parent unmounts this on a successful retry, so the pending timer has to
  // be cleared or it fires against a component that's gone.
  useEffect(() => () => window.clearTimeout(timerRef.current), []);

  function handleRetry() {
    if (retrying) return;
    setRetrying(true);
    onRetry();
    timerRef.current = window.setTimeout(() => setRetrying(false), MIN_FEEDBACK_MS);
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 16, flexWrap: "wrap" }}>
      <p style={{ color: "var(--warning-text)", margin: 0 }}>{message}</p>
      <Button
        variant="outline"
        onClick={handleRetry}
        disabled={retrying}
        style={{ padding: "6px 14px", fontSize: "var(--text-sm)" }}
      >
        {retrying ? "Retrying..." : "Retry"}
      </Button>
    </div>
  );
}
