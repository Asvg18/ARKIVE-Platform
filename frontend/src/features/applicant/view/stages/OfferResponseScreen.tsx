import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { ApplicationDetail } from "../../../../shared/api/applicant";
import { Button } from "../../../../shared/ui/Button";
import { ConfirmDialog } from "../../../../shared/ui/ConfirmDialog";
import { CheckIcon, ClockIcon } from "../../../../shared/ui/icons";
import { OnboardingScreen } from "./OnboardingScreen";

/** The screen an accepted applicant sees while their offer is still
 * unanswered, so they can confirm or decline it rather than meet a
 * "closed" line. This screen is the applicant's half of the offer.
 *
 * Three states, in the order an applicant meets them:
 *   unanswered — the offer, the countdown, Accept / Decline.
 *   accepted   — a confirmation line, then the onboarding checklist.
 *   expired    — never rendered here; the backend has already flipped the
 *                application to `withdrawn` by the time any read returns,
 *                so that case falls through to the closed-status line.
 *
 * A `hired` application with **no** offer at all is a legacy hire from
 * before this feature (see app/services/offers.py — absent deadline means
 * no window, deliberately, so a real hire is never auto-withdrawn by a
 * clock it was never given). Those go straight to the checklist. */
export function OfferResponseScreen({
  application,
  token,
  onUpdate,
}: {
  application: ApplicationDetail;
  token: string | null;
  onUpdate: (updated: ApplicationDetail) => void;
}) {
  const offer = application.offer;
  const answered = offer?.response ?? null;

  if (!offer || answered === "accepted") {
    return (
      <>
        <AcceptedHeader jobTitle={application.job_title} respondedToOffer={answered === "accepted"} />
        <div style={{ marginTop: 24, paddingTop: 24, borderTop: "1px solid var(--surface-border)" }}>
          <OnboardingScreen application={application} token={token} onUpdate={onUpdate} />
        </div>
      </>
    );
  }

  return <PendingOffer application={application} offer={offer} token={token} onUpdate={onUpdate} />;
}

/** `respondedToOffer` is false for a legacy hire — one accepted before
 * offers existed, which has no offer block to have answered. Saying "you
 * accepted the offer" to someone who was never given one to answer would
 * be inventing a step that did not happen. */
function AcceptedHeader({ jobTitle, respondedToOffer }: { jobTitle: string; respondedToOffer: boolean }) {
  return (
    <div>
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          padding: "6px 12px",
          borderRadius: 999,
          background: "var(--success-bg)",
          color: "var(--success-text)",
          fontFamily: "var(--arkive-font)",
          fontSize: "var(--text-xs)",
          fontWeight: 700,
          letterSpacing: "0.04em",
          textTransform: "uppercase",
        }}
      >
        <CheckIcon width={12} height={12} />
        {respondedToOffer ? "Offer Accepted" : "Accepted"}
      </div>
      <h2 style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xl)", fontWeight: 700, color: "var(--ink-900)", margin: "12px 0 0" }}>
        Welcome aboard!
      </h2>
      <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", margin: "6px 0 0", lineHeight: 1.55 }}>
        {respondedToOffer ? (
          <>
            You've accepted the offer for <strong style={{ color: "var(--ink-900)" }}>{jobTitle}</strong>. HR
            has been notified. Here's what's left to do before your first day.
          </>
        ) : (
          <>
            You've been accepted for <strong style={{ color: "var(--ink-900)" }}>{jobTitle}</strong>. Here's
            what's left to do before your first day.
          </>
        )}
      </p>
    </div>
  );
}

function PendingOffer({
  application,
  offer,
  token,
  onUpdate,
}: {
  application: ApplicationDetail;
  offer: NonNullable<ApplicationDetail["offer"]>;
  token: string | null;
  onUpdate: (updated: ApplicationDetail) => void;
}) {
  const [declineOpen, setDeclineOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<"accept" | "decline" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const remaining = useCountdown(offer.deadline);

  async function respond(action: "accept" | "decline") {
    setBusy(action);
    setError(null);
    try {
      const updated = await apiFetch<ApplicationDetail>(
        `/applicant/applications/${application.id}/offer/${action}`,
        {
          method: "POST",
          token,
          ...(action === "decline" ? { body: { reason: reason.trim() || null } } : {}),
        }
      );
      onUpdate(updated);
      setDeclineOpen(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not record your response.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          padding: "6px 12px",
          borderRadius: 999,
          background: "var(--success-bg)",
          color: "var(--success-text)",
          fontFamily: "var(--arkive-font)",
          fontSize: "var(--text-xs)",
          fontWeight: 700,
          letterSpacing: "0.04em",
          textTransform: "uppercase",
        }}
      >
        <CheckIcon width={12} height={12} />
        You've been accepted
      </div>

      <h2 style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xl)", fontWeight: 700, color: "var(--ink-900)", margin: "12px 0 0" }}>
        Congratulations, we'd like you to join us.
      </h2>
      <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", margin: "8px 0 0", lineHeight: 1.6 }}>
        MSEUF is offering you the position of{" "}
        <strong style={{ color: "var(--ink-900)" }}>{application.job_title}</strong> in{" "}
        {application.job_department}. Let us know whether you'd like to accept.
      </p>

      <CountdownPanel remaining={remaining} deadline={offer.deadline} windowDays={offer.window_days} />

      <div style={{ display: "flex", gap: 10, marginTop: 20, flexWrap: "wrap" }}>
        <Button variant="primary" disabled={busy !== null} onClick={() => respond("accept")}>
          {busy === "accept" ? "Accepting..." : "Accept Offer"}
        </Button>
        <Button
          variant="outline"
          disabled={busy !== null}
          onClick={() => {
            setError(null);
            setDeclineOpen(true);
          }}
          style={{ color: "var(--warning-text)", borderColor: "var(--warning-text)" }}
        >
          Decline Offer
        </Button>
      </div>

      {error && (
        <p style={{ fontFamily: "var(--arkive-font)", color: "crimson", fontSize: "var(--text-sm)", marginTop: 12 }}>{error}</p>
      )}

      <ConfirmDialog
        open={declineOpen}
        title="Decline this offer?"
        description={`This tells HR you're turning down the ${application.job_title} position. Your application will be closed as withdrawn, and you won't be able to undo this. You'd need to reapply.`}
        confirmLabel="Decline Offer"
        cancelLabel="Go Back"
        confirming={busy === "decline"}
        onConfirm={() => respond("decline")}
        onCancel={() => setDeclineOpen(false)}
      >
        <label
          style={{
            display: "block",
            fontFamily: "var(--arkive-font)",
            fontSize: "var(--text-2xs)",
            fontWeight: 700,
            color: "var(--ink-600)",
            textTransform: "uppercase",
            letterSpacing: "0.04em",
            marginBottom: 4,
          }}
        >
          Reason (optional)
        </label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          placeholder="e.g. I've accepted another role."
          style={{
            display: "block",
            width: "100%",
            padding: "8px 10px",
            borderRadius: "var(--radius)",
            border: "1px solid var(--surface-border)",
            background: "var(--surface)",
            fontFamily: "var(--arkive-font)",
            fontSize: "var(--text-sm)",
            color: "var(--ink-900)",
            boxSizing: "border-box",
            resize: "vertical",
          }}
        />
      </ConfirmDialog>
    </div>
  );
}

function CountdownPanel({
  remaining,
  deadline,
  windowDays,
}: {
  remaining: Remaining;
  deadline: string;
  windowDays: number;
}) {
  // Amber inside the last two days. The deadline is real — letting it pass
  // withdraws the application automatically — so the last stretch of it
  // should not look like the first.
  const urgent = remaining.totalMs <= 2 * 24 * 60 * 60 * 1000;
  const tone = urgent
    ? { bg: "var(--warning-bg)", text: "var(--warning-text)" }
    : { bg: "var(--surface-bg)", text: "var(--ink-900)" };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        marginTop: 20,
        padding: "14px 16px",
        borderRadius: "var(--radius)",
        background: tone.bg,
        border: `1px solid ${urgent ? "var(--warning-text)" : "var(--surface-border)"}`,
      }}
    >
      <ClockIcon width={18} height={18} style={{ color: tone.text, flexShrink: 0 }} />
      <div style={{ minWidth: 0 }}>
        <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", fontWeight: 700, color: tone.text, margin: 0 }}>
          {remaining.expired ? "This offer has expired." : `${remaining.label} left to respond`}
        </p>
        <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xs)", color: "var(--ink-600)", margin: "2px 0 0", lineHeight: 1.5 }}>
          {remaining.expired
            ? "Refresh the page to see the current status of your application."
            : `You have ${windowDays} days from the offer to reply, until ${formatDeadline(deadline)}. If we don't hear from you by then, the offer lapses and the application closes.`}
        </p>
      </div>
    </div>
  );
}

interface Remaining {
  label: string;
  totalMs: number;
  expired: boolean;
}

/** Ticks once a minute, not once a second. The window is measured in days
 * — a seconds-precise countdown would re-render sixty times more often to
 * animate a digit nobody is waiting on. */
function useCountdown(deadline: string): Remaining {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const totalMs = new Date(deadline).getTime() - now;
  if (!Number.isFinite(totalMs) || totalMs <= 0) {
    return { label: "No time", totalMs: 0, expired: true };
  }

  const minutes = Math.floor(totalMs / 60_000);
  const days = Math.floor(minutes / (60 * 24));
  const hours = Math.floor((minutes % (60 * 24)) / 60);
  if (days > 0) {
    return { label: `${days} ${plural(days, "day")}, ${hours} ${plural(hours, "hour")}`, totalMs, expired: false };
  }
  if (hours > 0) {
    const mins = minutes % 60;
    return { label: `${hours} ${plural(hours, "hour")}, ${mins} ${plural(mins, "minute")}`, totalMs, expired: false };
  }
  return { label: `${minutes} ${plural(minutes, "minute")}`, totalMs, expired: false };
}

function plural(count: number, noun: string): string {
  return count === 1 ? noun : `${noun}s`;
}

function formatDeadline(deadline: string): string {
  return new Date(deadline).toLocaleString(undefined, {
    dateStyle: "long",
    timeStyle: "short",
  });
}
