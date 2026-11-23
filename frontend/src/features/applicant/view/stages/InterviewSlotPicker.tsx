import { useState } from "react";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { ApplicationDetail, InterviewSlotOffer } from "../../../../shared/api/applicant";
import { formatDay, formatWindow } from "../../../../shared/lib/scheduleTime";
import { Alert } from "../../../../shared/ui/Alert";
import { Button } from "../../../../shared/ui/Button";
import { CalendarPicker } from "../../../../shared/ui/CalendarPicker";
import { ConfirmDialog } from "../../../../shared/ui/ConfirmDialog";
import { ClockIcon } from "../../../../shared/ui/icons";

/** The applicant picks their interview time from the ones HR sent: a
 *  date first — only days with a
 *  free slot can be pressed — then the time. Picking is confirming, so it
 *  asks once. "None of these work" tells HR, who send others; it never
 *  withdraws the application. */
export function InterviewSlotPicker({
  application,
  offer,
  stageName,
  token,
  onUpdate,
}: {
  application: ApplicationDetail;
  offer: InterviewSlotOffer;
  stageName: string;
  token: string | null;
  onUpdate: (updated: ApplicationDetail) => void;
}) {
  const days = new Set(offer.slots.map((s) => s.date));
  const [day, setDay] = useState<string | null>(null);
  const [time, setTime] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [decliningOpen, setDecliningOpen] = useState(false);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const chosen = offer.slots.find((s) => s.date === day && s.time === time) ?? null;
  const where = offer.mode === "online" ? "Online (the meeting link appears here once you pick)" : offer.location ?? "";

  async function post(path: string, body: Record<string, unknown>) {
    setSubmitting(true);
    setError(null);
    try {
      const updated = await apiFetch<ApplicationDetail>(`/applicant/applications/${application.id}/${path}`, {
        method: "POST",
        token,
        body: { stage_type: offer.stage_type, ...body },
      });
      setConfirming(false);
      onUpdate(updated);
    } catch (err) {
      setConfirming(false);
      setError(err instanceof ApiError ? err.message : "Could not send your answer. Please try again.");
      // The time may have just gone to someone else — show what's left.
      setTime(null);
      apiFetch<ApplicationDetail>(`/applicant/applications/${application.id}`, { token })
        .then(onUpdate)
        .catch(() => undefined);
    } finally {
      setSubmitting(false);
    }
  }

  if (offer.response === "none_work") {
    return (
      <div>
        <h2 style={heading}>{stageName}</h2>
        <div style={{ marginTop: 16 }}>
          <Alert
            tone="warning"
            title="You've told HR none of these times work."
          >
            Your application is still open. They'll send you other times to choose from.
          </Alert>
        </div>
      </div>
    );
  }

  if (offer.slots.length === 0) {
    return (
      <div>
        <h2 style={heading}>{stageName}</h2>
        <p style={subtext}>The times HR sent have all been taken. HR will send you more.</p>
      </div>
    );
  }

  const daySlots = day ? offer.slots.filter((s) => s.date === day) : [];

  return (
    <div>
      <h2 style={heading}>{stageName}</h2>
      <p style={subtext}>
        Pick a time for your interview: a date, then a time. Each lasts {offer.duration_minutes} minutes. {where}.
      </p>

      <div className="ark-book">
        <CalendarPicker
          label="Interview dates with a free time"
          selected={day ? [day] : []}
          isEnabled={(d) => days.has(d)}
          onPick={(d) => {
            setDay(d);
            setTime(null);
            setError(null);
          }}
        />
        <div>
          {day ? (
            <>
              <p className="ark-book__day">{formatDay(day)}</p>
              <div className="ark-choices ark-choices--stack" role="radiogroup" aria-label={`Times on ${formatDay(day)}`}>
                {daySlots.map((slot) => (
                  <button
                    key={slot.time}
                    type="button"
                    role="radio"
                    aria-checked={slot.time === time}
                    className="ark-choice"
                    onClick={() => setTime(slot.time)}
                  >
                    <span className="ark-choice__icon" aria-hidden="true">
                      <ClockIcon width={18} height={18} />
                    </span>
                    <span className="ark-choice__text">
                      <span className="ark-choice__title">{formatWindow(slot.time, slot.end_time)}</span>
                    </span>
                    <span className="ark-choice__radio" aria-hidden="true" />
                  </button>
                ))}
              </div>
            </>
          ) : (
            <p className="ark-book__hint">Pick a date to see its times.</p>
          )}
        </div>
      </div>

      {error && <p style={{ color: "crimson", fontSize: "var(--text-sm)", marginTop: 12 }}>{error}</p>}

      {decliningOpen ? (
        <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--surface-border)" }}>
          <p style={{ ...subtext, marginTop: 0 }}>
            HR will send other times. Telling them doesn't withdraw your application.
          </p>
          <textarea
            className="ark-input"
            rows={3}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Optional: anything that helps them pick better times."
            style={{ marginTop: 8 }}
          />
          <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
            <Button variant="primary" disabled={submitting} onClick={() => post("interview-slot/decline", { note })}>
              {submitting ? "Sending..." : "Send to HR"}
            </Button>
            <Button variant="secondary" disabled={submitting} onClick={() => setDecliningOpen(false)}>
              Go Back
            </Button>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", gap: 10, marginTop: 20, flexWrap: "wrap" }}>
          <Button variant="primary" disabled={!chosen || submitting} onClick={() => setConfirming(true)}>
            Confirm This Time
          </Button>
          <Button variant="outline" disabled={submitting} onClick={() => setDecliningOpen(true)}>
            None of These Work for Me
          </Button>
        </div>
      )}

      <ConfirmDialog
        open={confirming && chosen != null}
        title="Confirm this time?"
        description={
          chosen
            ? `${formatDay(chosen.date)}, ${formatWindow(chosen.time, chosen.end_time)}. ` +
              "This confirms you'll attend. To change it later, contact the HR office."
            : ""
        }
        confirmLabel="Confirm Time"
        confirming={submitting}
        onCancel={() => setConfirming(false)}
        onConfirm={() => chosen && post("interview-slot", { date: chosen.date, time: chosen.time })}
      />
    </div>
  );
}

const heading: React.CSSProperties = { fontFamily: "var(--arkive-font)", fontSize: "var(--text-xl)", fontWeight: 700, color: "var(--ink-900)", margin: 0 };
const subtext: React.CSSProperties = { fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", marginTop: 6 };
