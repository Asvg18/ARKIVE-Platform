import { useState, type FormEvent } from "react";
import { apiFetch, ApiError } from "../../../../../shared/api/client";
import type { InterviewDetail } from "../../../../../shared/api/evaluator";
import { Alert } from "../../../../../shared/ui/Alert";
import { Button } from "../../../../../shared/ui/Button";
import { AlertIcon, CalendarIcon, ClockIcon, MapPinIcon, VideoIcon } from "../../../../../shared/ui/icons";
import { minTimeFor, todayInPhilippines } from "../../../../../shared/lib/scheduleTime";
import { formatDate, formatTime, type ScheduleInfo } from "./interviewFormat";

/** When, where, and — while the round is open — the way to ask HR to
 * move it. */
export function SchedulePanel({
  interview,
  canReschedule,
  token,
  onUpdate,
}: {
  interview: InterviewDetail;
  canReschedule: boolean;
  token: string | null;
  onUpdate: (updated: InterviewDetail) => void;
}) {
  const [formOpen, setFormOpen] = useState(false);
  const [proposedDate, setProposedDate] = useState("");
  const [proposedTime, setProposedTime] = useState("");
  const [reason, setReason] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const schedule = interview.schedule as ScheduleInfo | null;
  const online = schedule?.mode === "online";
  const pending = interview.pending_reschedule_request;

  async function handleRequest(e: FormEvent) {
    e.preventDefault();
    setSending(true);
    setError(null);
    try {
      const updated = await apiFetch<InterviewDetail>(
        `/evaluator/interviews/${interview.stage_instance_id}/reschedule-request`,
        {
          method: "POST",
          token,
          body: { proposed_date: proposedDate, proposed_time: proposedTime, reason: reason || null },
        }
      );
      onUpdate(updated);
      setFormOpen(false);
      setProposedDate("");
      setProposedTime("");
      setReason("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit the request.");
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="ark-panel" aria-labelledby="eval-schedule-title">
      <div className="ark-panel__head">
        <h2 id="eval-schedule-title" className="ark-panel__title">Interview schedule</h2>
      </div>
      <div className="ark-panel__body">
        {schedule ? (
          <ul className="ark-eval-facts">
            <li>
              <span className="ark-eval-facts__icon" aria-hidden="true">
                <CalendarIcon width={16} height={16} />
              </span>
              <span>
                <small>Date</small>
                {formatDate(schedule.date) ?? "–"}
              </span>
            </li>
            <li>
              <span className="ark-eval-facts__icon" aria-hidden="true">
                <ClockIcon width={16} height={16} />
              </span>
              <span>
                <small>Time</small>
                {formatTime(schedule.time) ?? "–"}
              </span>
            </li>
            <li>
              <span className="ark-eval-facts__icon" aria-hidden="true">
                {online ? <VideoIcon width={16} height={16} /> : <MapPinIcon width={16} height={16} />}
              </span>
              <span>
                <small>{online ? "Online" : "Location"}</small>
                {online ? (
                  schedule.meeting_link ? (
                    <a href={schedule.meeting_link} target="_blank" rel="noreferrer" className="ark-eval-facts__link">
                      {schedule.meeting_link}
                    </a>
                  ) : (
                    "Meeting link not set yet"
                  )
                ) : (
                  schedule.location || "–"
                )}
              </span>
            </li>
          </ul>
        ) : (
          <p className="ark-panel__empty">Not scheduled yet. HR sets the time and place.</p>
        )}

        {pending ? (
          <div className="ark-eval-pending" role="status">
            <AlertIcon width={16} height={16} aria-hidden="true" />
            <div>
              <strong>Reschedule requested, waiting on HR</strong>
              <span>
                You proposed {formatDate(pending.proposed_date)} at {formatTime(pending.proposed_time)}
                {pending.reason && ` ("${pending.reason}")`}
              </span>
            </div>
          </div>
        ) : (
          // Not for an upcoming round: there may be no schedule to
          // move yet, and the round isn't the evaluator's to act on
          // until the candidate reaches it.
          canReschedule && (
            <div className="ark-eval-reschedule">
              {formOpen ? (
                <form onSubmit={handleRequest} className="ark-fields" style={{ gap: "var(--space-3)" }}>
                  {/* One above the other: a date field won't fit in half
                      of a rail card. */}
                  <label className="ark-field">
                    <span className="ark-field__label">New date</span>
                    <input
                      type="date"
                      required
                      min={todayInPhilippines()}
                      className="ark-input"
                      value={proposedDate}
                      onChange={(e) => setProposedDate(e.target.value)}
                    />
                  </label>
                  <label className="ark-field">
                    <span className="ark-field__label">New time</span>
                    <input
                      type="time"
                      required
                      min={minTimeFor(proposedDate)}
                      className="ark-input"
                      value={proposedTime}
                      onChange={(e) => setProposedTime(e.target.value)}
                    />
                  </label>
                  <label className="ark-field">
                    <span className="ark-field__label">
                      Reason <span className="ark-field__req">Optional</span>
                    </span>
                    <input
                      type="text"
                      className="ark-input"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                  </label>
                  {error && <Alert tone="danger" title="The request wasn't sent">{error}</Alert>}
                  <div style={{ display: "flex", gap: "var(--space-2)" }}>
                    <Button type="submit" variant="primary" size="sm" disabled={sending}>
                      {sending ? "Sending..." : "Send to HR"}
                    </Button>
                    <Button type="button" variant="ghost" size="sm" onClick={() => setFormOpen(false)} disabled={sending}>
                      Cancel
                    </Button>
                  </div>
                </form>
              ) : (
                <Button variant="secondary" size="sm" onClick={() => setFormOpen(true)}>
                  Request a new time
                </Button>
              )}
            </div>
          )
        )}
      </div>
    </section>
  );
}
