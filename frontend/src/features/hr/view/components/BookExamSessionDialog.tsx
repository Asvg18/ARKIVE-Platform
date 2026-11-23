import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { CandidateProfile, ExamSlot, StageType } from "../../../../shared/api/pipeline";
import { formatDay, formatWindow } from "../../../../shared/lib/scheduleTime";
import { Button } from "../../../../shared/ui/Button";
import { Modal } from "../../../../shared/ui/Modal";
import { hasStarted } from "../../model/examSessions";

/** HR books an applicant into one of the job's exam sessions, or moves
 *  them to another. There is no one-off time: every exam is a seat in a
 *  real session.
 *  HR isn't held to the applicant's 24-hour cut-off, only to free seats;
 *  the applicant is told either way. */
export function BookExamSessionDialog({
  open,
  applicationId,
  applicantName,
  requisitionId,
  stageType,
  stageLabel,
  currentSlotId,
  token,
  onClose,
  onBooked,
}: {
  open: boolean;
  applicationId: number;
  applicantName: string;
  requisitionId: number;
  stageType: string;
  stageLabel: string;
  /** The session they're in now, when this is a move. */
  currentSlotId: number | null;
  token: string | null;
  onClose: () => void;
  onBooked: (profile: CandidateProfile) => void;
}) {
  const [sessions, setSessions] = useState<ExamSlot[] | null>(null);
  const [chosen, setChosen] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setChosen(null);
    setError(null);
    setSessions(null);
    apiFetch<ExamSlot[]>(`/hr/requisitions/${requisitionId}/exam-slots`, { token })
      .then((all) => setSessions(all.filter((s) => s.stage_type === stageType && !hasStarted(s))))
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load the sessions."));
  }, [open, requisitionId, stageType, token]);

  const days = [...new Set((sessions ?? []).map((s) => s.date))];
  const moving = currentSlotId != null;

  async function book() {
    if (chosen == null) return;
    setSubmitting(true);
    setError(null);
    try {
      const profile = await apiFetch<CandidateProfile>(`/hr/applications/${applicationId}/exam-booking`, {
        method: "POST",
        token,
        body: { stage_type: stageType as StageType, exam_slot_id: chosen },
      });
      onBooked(profile);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not book this session.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title={moving ? `Move ${applicantName} to another session` : `Book a session for ${applicantName}`}
      sub={`${stageLabel}. ${applicantName} gets a notification and an email.`}
      busy={submitting}
      width={560}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" onClick={book} disabled={submitting || chosen == null}>
            {submitting ? "Booking..." : moving ? "Move Here" : "Book Session"}
          </Button>
        </>
      }
    >
      {sessions == null && !error && <p className="ark-field__hint">Loading the sessions...</p>}
      {sessions != null && sessions.length === 0 && (
        <p className="ark-panel__empty">There are no sessions coming up for this exam. Add some first.</p>
      )}
      {days.length > 0 && (
        <div className="ark-book-list" role="radiogroup" aria-label="Exam sessions">
          {days.map((day) => (
            <div key={day}>
              <p className="ark-book-list__day">{formatDay(day)}</p>
              {(sessions ?? [])
                .filter((s) => s.date === day)
                .map((s) => {
                  const current = s.id === currentSlotId;
                  const full = s.remaining_capacity <= 0;
                  return (
                    <label key={s.id} className="ark-book-option" data-disabled={current || full || undefined}>
                      <input
                        type="radio"
                        name="exam-session"
                        value={s.id}
                        checked={chosen === s.id}
                        disabled={current || full}
                        onChange={() => setChosen(s.id)}
                      />
                      <span className="ark-book-option__text">
                        <span className="ark-book-option__when">{formatWindow(s.time, s.end_time)}</span>
                        <span className="ark-book-option__where">{s.location}</span>
                      </span>
                      <span className="ark-book-option__seats">
                        {current ? "Booked here now" : full ? "Full" : `${s.remaining_capacity} of ${s.capacity} seats left`}
                      </span>
                    </label>
                  );
                })}
            </div>
          ))}
        </div>
      )}
      {error && <p className="ark-form-error">{error}</p>}
    </Modal>
  );
}
