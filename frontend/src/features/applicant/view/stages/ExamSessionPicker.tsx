import { useState } from "react";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { ApplicationDetail, ExamBookingSummary } from "../../../../shared/api/applicant";
import { formatDay, formatWindow } from "../../../../shared/lib/scheduleTime";
import { Button } from "../../../../shared/ui/Button";
import { CalendarPicker } from "../../../../shared/ui/CalendarPicker";
import { ConfirmDialog } from "../../../../shared/ui/ConfirmDialog";
import { AlertIcon, ClockIcon } from "../../../../shared/ui/icons";

/** The applicant books their exam: a
 *  date first (only days with a free seat can be pressed), then one of
 *  that day's sessions. Booking takes effect at once, with no HR
 *  approval. They can change it here until 24 hours before it starts
 *  (`changing`), and if no session works they can tell HR, who is
 *  notified; adding sessions tells them in turn. It asks once before
 *  booking. */
export function ExamSessionPicker({
  application,
  stageType,
  stageName,
  token,
  onUpdate,
  changing,
  onCancelChange,
}: {
  application: ApplicationDetail;
  stageType: string;
  stageName: string;
  token: string | null;
  onUpdate: (updated: ApplicationDetail) => void;
  /** The booking being changed; absent for a first booking. */
  changing?: ExamBookingSummary;
  onCancelChange?: () => void;
}) {
  const sessions = application.exam_sessions;
  const days = new Set(sessions.map((s) => s.date));
  const [day, setDay] = useState<string | null>(null);
  const [slotId, setSlotId] = useState<number | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [noneOpen, setNoneOpen] = useState(false);
  const [noneNote, setNoneNote] = useState("");
  const [noneSending, setNoneSending] = useState(false);

  const chosen = sessions.find((s) => s.id === slotId) ?? null;
  const noneWork = application.exam_none_work;

  async function book() {
    if (!chosen) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await apiFetch<ApplicationDetail>(`/applicant/applications/${application.id}/exam-booking`, {
        method: changing ? "PUT" : "POST",
        token,
        body: { stage_type: stageType, exam_slot_id: chosen.id },
      });
      setConfirming(false);
      onUpdate(updated);
    } catch (err) {
      setConfirming(false);
      setError(err instanceof ApiError ? err.message : "Could not book this session. Please try again.");
      // The seat may have just gone to someone else: show what's left.
      setSlotId(null);
      apiFetch<ApplicationDetail>(`/applicant/applications/${application.id}`, { token })
        .then(onUpdate)
        .catch(() => undefined);
    } finally {
      setSubmitting(false);
    }
  }

  async function sayNoneWork() {
    setNoneSending(true);
    setError(null);
    try {
      const updated = await apiFetch<ApplicationDetail>(
        `/applicant/applications/${application.id}/exam-booking/none-work`,
        { method: "POST", token, body: { stage_type: stageType, note: noneNote.trim() || null } }
      );
      setNoneOpen(false);
      setNoneNote("");
      onUpdate(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send this. Please try again.");
    } finally {
      setNoneSending(false);
    }
  }

  const daySessions = day ? sessions.filter((s) => s.date === day) : [];

  return (
    <div>
      <h2 className="ark-stage-title">{stageName}</h2>
      {changing ? (
        <p className="ark-stage-sub">
          Pick another session. You're booked for {formatDay(changing.date)}, {formatWindow(changing.time, changing.end_time)}{" "}
          until you confirm the new one.
        </p>
      ) : (
        <p className="ark-stage-sub">Book your exam: pick a date, then a time. Only dates with a free seat can be picked.</p>
      )}

      {!changing && noneWork && (
        <div className="ark-stage-note" role="status">
          <AlertIcon width={16} height={16} aria-hidden="true" />
          <span>
            You told HR none of the sessions work{noneWork.note ? ` ("${noneWork.note}")` : ""}. You'll be notified when new
            ones open, and you can still pick one below.
          </span>
        </div>
      )}

      {sessions.length === 0 ? (
        <p className="ark-stage-sub">
          {changing
            ? "There are no other sessions with a free seat right now."
            : "No exam sessions are open yet. HR will add them, and you'll be notified when they do."}
        </p>
      ) : (
        <div className="ark-book">
          <CalendarPicker
            label="Exam dates with a free seat"
            selected={day ? [day] : []}
            isEnabled={(d) => days.has(d)}
            onPick={(d) => {
              setDay(d);
              setSlotId(null);
              setError(null);
            }}
          />
          <div>
            {day ? (
              <>
                <p className="ark-book__day">{formatDay(day)}</p>
                <div className="ark-choices ark-choices--stack" role="radiogroup" aria-label={`Sessions on ${formatDay(day)}`}>
                  {daySessions.map((session) => (
                    <button
                      key={session.id}
                      type="button"
                      role="radio"
                      aria-checked={session.id === slotId}
                      className="ark-choice"
                      onClick={() => setSlotId(session.id)}
                    >
                      <span className="ark-choice__icon" aria-hidden="true">
                        <ClockIcon width={18} height={18} />
                      </span>
                      <span className="ark-choice__text">
                        <span className="ark-choice__title">{formatWindow(session.time, session.end_time)}</span>
                        <span className="ark-choice__desc">
                          {session.location} · {session.remaining_capacity}{" "}
                          {session.remaining_capacity === 1 ? "seat" : "seats"} left
                        </span>
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
      )}

      {error && <p className="ark-form-error" style={{ marginTop: 12 }}>{error}</p>}

      <div className="ark-stage-actions">
        {sessions.length > 0 && (
          <Button variant="primary" disabled={!chosen || submitting} onClick={() => setConfirming(true)}>
            {changing ? "Change to This Session" : "Book This Session"}
          </Button>
        )}
        {changing && onCancelChange && (
          <Button variant="secondary" onClick={onCancelChange} disabled={submitting}>
            Keep My Session
          </Button>
        )}
        {/* A proper button, as on the interview time picker, not a quiet
            link: it is one of the two answers this screen asks for. */}
        {!changing && !noneWork && (
          <Button type="button" variant="outline" onClick={() => setNoneOpen((open) => !open)} aria-expanded={noneOpen}>
            None of These Work for Me
          </Button>
        )}
      </div>

      {noneOpen && (
        <div className="ark-stage-panel">
          <label className="ark-field">
            <span className="ark-field__label">
              Tell HR why <span className="ark-field__req">Optional</span>
            </span>
            <textarea
              className="ark-input"
              rows={2}
              maxLength={500}
              value={noneNote}
              onChange={(e) => setNoneNote(e.target.value)}
              placeholder="e.g. I work on weekdays until 5 PM"
            />
          </label>
          <div className="ark-stage-actions">
            <Button variant="secondary" onClick={sayNoneWork} disabled={noneSending}>
              {noneSending ? "Sending..." : "Tell HR"}
            </Button>
            <Button variant="ghost" onClick={() => setNoneOpen(false)} disabled={noneSending}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirming && chosen != null}
        title={changing ? "Change to this session?" : "Book this session?"}
        description={
          chosen
            ? `${formatDay(chosen.date)}, ${formatWindow(chosen.time, chosen.end_time)}, at ${chosen.location}. ` +
              (changing
                ? "Your current booking is given up."
                : "You can change it here until 24 hours before it starts.")
            : ""
        }
        confirmLabel={changing ? "Change Session" : "Book Session"}
        confirming={submitting}
        onCancel={() => setConfirming(false)}
        onConfirm={book}
      />
    </div>
  );
}
