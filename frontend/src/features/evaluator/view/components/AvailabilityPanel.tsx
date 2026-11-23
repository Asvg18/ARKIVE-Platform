import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { InterviewDetail } from "../../../../shared/api/evaluator";
import { formatDay, formatWindow, minTimeFor, todayInPhilippines } from "../../../../shared/lib/scheduleTime";
import { Button } from "../../../../shared/ui/Button";
import { PlusIcon, XIcon } from "../../../../shared/ui/icons";

interface Range {
  date: string;
  start: string;
  end: string;
}

function sameRanges(a: Range[], b: Range[]): boolean {
  return a.length === b.length && a.every((r, i) => r.date === b[i].date && r.start === b[i].start && r.end === b[i].end);
}

function sorted(ranges: Range[]): Range[] {
  return [...ranges].sort((x, y) => (x.date + x.start).localeCompare(y.date + y.start));
}

/** "My availability": the
 *  ranges this evaluator is free in for one candidate's round. HR cuts
 *  them into slots of the round's length and sends the ones it wants to
 *  the applicant, who picks one. Open from the moment they're assigned,
 *  and saved as a whole set — removing a range is just leaving it out.
 *  Hidden by the page once the time is booked. */
export function AvailabilityPanel({
  interview,
  token,
  onUpdate,
}: {
  interview: InterviewDetail;
  token: string | null;
  onUpdate: (updated: InterviewDetail) => void;
}) {
  const [ranges, setRanges] = useState<Range[]>(interview.availability);
  const [date, setDate] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => setRanges(interview.availability), [interview.availability]);

  const dirty = !sameRanges(sorted(ranges), sorted(interview.availability));
  const minutes = interview.duration_minutes;

  function addRange() {
    setError(null);
    setSaved(false);
    if (!date || !start || !end) {
      setError("Pick a date, a start and an end time.");
      return;
    }
    if (end <= start) {
      setError("A range has to end after it starts.");
      return;
    }
    if (ranges.some((r) => r.date === date && r.start < end && start < r.end)) {
      setError("That overlaps a range you already have on this day. Change that one instead.");
      return;
    }
    setRanges((prev) => sorted([...prev, { date, start, end }]));
    setStart("");
    setEnd("");
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const updated = await apiFetch<InterviewDetail>(
        `/evaluator/interviews/${interview.stage_instance_id}/availability`,
        { method: "PUT", token, body: { windows: ranges } }
      );
      onUpdate(updated);
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save your times.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="ark-panel" aria-labelledby="eval-availability-title">
      <div className="ark-panel__head">
        <div>
          <h2 id="eval-availability-title" className="ark-panel__title">My availability</h2>
          <p className="ark-panel__sub">
            When you're free for this interview. HR cuts it into {minutes}-minute slots and sends them to{" "}
            {interview.applicant_name}, who picks one.
          </p>
        </div>
        <span className="ark-panel__count">
          {interview.availability.length} {interview.availability.length === 1 ? "range" : "ranges"} saved
        </span>
      </div>
      <div className="ark-panel__body">
        {interview.times_sent && (
          <p className="ark-field__hint" style={{ marginBottom: "var(--space-3)" }}>
            HR has sent your times to the applicant. They'll appear under Interview schedule once one is picked.
          </p>
        )}
        {ranges.length > 0 ? (
          <ul className="ark-sessions">
            {ranges.map((range, index) => (
              <li key={`${range.date}-${range.start}-${index}`} className="ark-session">
                {/* The same row the exam sessions panel draws: the day
                    and window, then the remove button at the end. */}
                <div className="ark-session__row">
                  <span className="ark-session__text">
                    <span className="ark-session__when">{formatDay(range.date)}</span>
                    <span className="ark-session__where">{formatWindow(range.start, range.end)}</span>
                  </span>
                  <button
                    type="button"
                    className="ark-icon-btn"
                    aria-label={`Remove ${formatDay(range.date)}, ${formatWindow(range.start, range.end)}`}
                    onClick={() => {
                      setSaved(false);
                      setRanges((prev) => prev.filter((_, i) => i !== index));
                    }}
                  >
                    <XIcon width={14} height={14} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="ark-panel__empty">No times yet. Add the ranges you're free in below.</p>
        )}

        <div className="ark-window" style={{ flexWrap: "wrap", marginTop: "var(--space-4)" }}>
          <input
            type="date"
            className="ark-input"
            aria-label="Date"
            min={todayInPhilippines()}
            value={date}
            onChange={(e) => setDate(e.target.value)}
            style={{ width: 170 }}
          />
          <input
            type="time"
            className="ark-input"
            aria-label="From"
            min={minTimeFor(date)}
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
          <span className="ark-window__dash">to</span>
          <input type="time" className="ark-input" aria-label="Until" value={end} onChange={(e) => setEnd(e.target.value)} />
          <Button variant="secondary" size="sm" onClick={addRange}>
            <PlusIcon width={14} height={14} /> Add
          </Button>
        </div>
        {error && <p className="ark-interview__error">{error}</p>}
      </div>
      <div className="ark-panel__foot ark-panel__foot--actions">
        {saved && !dirty && <span className="ark-field__hint">Saved.</span>}
        {dirty && <span className="ark-field__hint" style={{ color: "var(--warning-text)" }}>Unsaved changes</span>}
        <Button variant="primary" size="sm" disabled={!dirty || saving} onClick={save}>
          {saving ? "Saving..." : "Save availability"}
        </Button>
      </div>
    </section>
  );
}
