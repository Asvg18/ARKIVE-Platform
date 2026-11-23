import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { ExamSessionUpdateRequest, ExamSlot } from "../../../../shared/api/pipeline";
import { minTimeFor, todayInPhilippines } from "../../../../shared/lib/scheduleTime";
import { Button } from "../../../../shared/ui/Button";
import { Modal } from "../../../../shared/ui/Modal";
import { windowProblem } from "../../model/examSessions";

/** HR edits one exam session: its day,
 *  time window, place or seats. Everyone booked in it is told when the
 *  day, time or place changes, and seats can't go below the number
 *  already booked. */
export function EditExamSessionDialog({
  session,
  requisitionId,
  token,
  onClose,
  onSaved,
}: {
  session: ExamSlot | null;
  requisitionId: number;
  token: string | null;
  onClose: () => void;
  onSaved: (updated: ExamSlot) => void;
}) {
  const [date, setDate] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [location, setLocation] = useState("");
  const [seats, setSeats] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    setDate(session.date);
    setStart(session.time);
    setEnd(session.end_time ?? "");
    setLocation(session.location);
    setSeats(String(session.capacity));
    setError(null);
  }, [session]);

  const booked = session ? session.booked.length : 0;

  async function submit() {
    if (!session) return;
    const seatCount = Number(seats);
    const problem =
      !date
        ? "Pick the day."
        : windowProblem([{ start, end }]) ??
          (!Number.isInteger(seatCount) || seatCount < 1 ? "Enter how many seats it has." : null) ??
          (seatCount < booked ? `${booked} ${booked === 1 ? "person has" : "people have"} booked it, so it needs at least ${booked} ${booked === 1 ? "seat" : "seats"}.` : null) ??
          (!location.trim() ? "Enter where the exam takes place." : null);
    if (problem) {
      setError(problem);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const body: ExamSessionUpdateRequest = { date, start, end, location: location.trim(), seats: seatCount };
      const updated = await apiFetch<ExamSlot>(`/hr/requisitions/${requisitionId}/exam-slots/${session.id}`, {
        method: "PATCH",
        token,
        body,
      });
      onSaved(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save this session.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={session != null}
      title="Edit session"
      sub={
        booked > 0
          ? `${booked} ${booked === 1 ? "person has" : "people have"} booked this session. They'll be told if the day, time or place changes.`
          : "Nobody has booked this session yet."
      }
      busy={submitting}
      width={520}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} disabled={submitting}>
            {submitting ? "Saving..." : "Save Changes"}
          </Button>
        </>
      }
    >
      <div className="ark-fields">
        <label className="ark-field">
          <span className="ark-field__label">Day</span>
          <input type="date" className="ark-input" min={todayInPhilippines()} value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <div className="ark-fields ark-fields--2">
          <label className="ark-field">
            <span className="ark-field__label">Starts</span>
            <input type="time" className="ark-input" min={minTimeFor(date)} value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label className="ark-field">
            <span className="ark-field__label">Ends</span>
            <input type="time" className="ark-input" value={end} onChange={(e) => setEnd(e.target.value)} />
          </label>
        </div>
        <div className="ark-fields ark-fields--2">
          <label className="ark-field">
            <span className="ark-field__label">Seats</span>
            <input type="number" min={Math.max(1, booked)} max={500} className="ark-input" value={seats} onChange={(e) => setSeats(e.target.value)} />
          </label>
          <label className="ark-field">
            <span className="ark-field__label">Location</span>
            <input type="text" className="ark-input" value={location} onChange={(e) => setLocation(e.target.value)} />
          </label>
        </div>
        {error && <p className="ark-form-error">{error}</p>}
      </div>
    </Modal>
  );
}
