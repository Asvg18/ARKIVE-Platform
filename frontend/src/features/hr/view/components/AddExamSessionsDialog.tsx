import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type {
  ExamSessionBatchRequest,
  ExamSessionBatchResult,
  ExamSlot,
  RequisitionDetail,
  StageType,
} from "../../../../shared/api/pipeline";
import { formatDay, formatWindow, todayInPhilippines } from "../../../../shared/lib/scheduleTime";
import { jobStageLabel } from "../../../../shared/lib/stageLabels";
import { Button } from "../../../../shared/ui/Button";
import { CalendarPicker } from "../../../../shared/ui/CalendarPicker";
import { Modal } from "../../../../shared/ui/Modal";
import { PlusIcon, XIcon } from "../../../../shared/ui/icons";
import { MAX_DATES, WINDOW_PRESETS, datesBetween, previewSessions, windowProblem, type WindowDraft } from "../../model/examSessions";

type DateMode = "days" | "range";

/** HR's "Add sessions": the days the
 *  exam runs, one or more time windows, the seats and the place. Every
 *  day × every window becomes a session, created together.
 *
 *  Built so HR never types sessions one by one: days are pressed on a
 *  calendar or filled from a date range (weekdays only, if wanted), the
 *  usual windows are one click, and a preview shows exactly what will be
 *  made, including any session the job already has (skipped, not
 *  duplicated). Used from the job's page and from a candidate's profile. */
export function AddExamSessionsDialog({
  open,
  job,
  examStages,
  initialStage,
  existing,
  token,
  onClose,
  onAdded,
}: {
  open: boolean;
  job: RequisitionDetail;
  examStages: string[];
  /** The exam to start on, e.g. the one a candidate's profile is showing. */
  initialStage?: string;
  /** The job's sessions so far, to mark repeats in the preview. */
  existing: ExamSlot[];
  token: string | null;
  onClose: () => void;
  onAdded: (result: ExamSessionBatchResult) => void;
}) {
  const [stage, setStage] = useState(initialStage ?? examStages[0]);
  const [mode, setMode] = useState<DateMode>("days");
  const [dates, setDates] = useState<string[]>([]);
  const [rangeFrom, setRangeFrom] = useState("");
  const [rangeTo, setRangeTo] = useState("");
  const [weekdaysOnly, setWeekdaysOnly] = useState(true);
  const [windows, setWindows] = useState<WindowDraft[]>([{ ...WINDOW_PRESETS[0] }]);
  const [seats, setSeats] = useState("");
  const [location, setLocation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setStage(initialStage ?? examStages[0]);
    setMode("days");
    setDates([]);
    setRangeFrom("");
    setRangeTo("");
    setWeekdaysOnly(true);
    setWindows([{ start: WINDOW_PRESETS[0].start, end: WINDOW_PRESETS[0].end }]);
    setSeats("");
    setLocation("");
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const today = todayInPhilippines();
  const rangeDays = datesBetween(rangeFrom, rangeTo, weekdaysOnly).filter((day) => day >= today);
  const chosenDays = mode === "days" ? dates : rangeDays;
  const preview = previewSessions(stage, chosenDays, windows, location, existing);
  const toCreate = preview.filter((p) => !p.exists).length;
  const repeats = preview.length - toCreate;

  function toggleDate(day: string) {
    setDates((prev) => (prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day].sort()));
  }

  function updateWindow(index: number, patch: Partial<WindowDraft>) {
    setWindows((prev) => prev.map((w, i) => (i === index ? { ...w, ...patch } : w)));
  }

  function addPreset(start: string, end: string) {
    setWindows((prev) => (prev.some((w) => w.start === start && w.end === end) ? prev : [...prev, { start, end }]));
  }

  async function submit() {
    const seatCount = Number(seats);
    const problem =
      chosenDays.length === 0
        ? mode === "days"
          ? "Pick at least one date."
          : "Pick a date range with at least one day still to come."
        : chosenDays.length > MAX_DATES
        ? `Pick up to ${MAX_DATES} days at a time.`
        : windowProblem(windows) ??
          (!Number.isInteger(seatCount) || seatCount < 1 ? "Enter how many seats each session has." : null) ??
          (!location.trim() ? "Enter where the exam takes place." : null) ??
          (toCreate === 0 ? "The job already has all of these sessions." : null);
    if (problem) {
      setError(problem);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const body: ExamSessionBatchRequest = {
        stage_type: stage as StageType,
        dates: chosenDays,
        windows,
        seats: seatCount,
        location: location.trim(),
      };
      const result = await apiFetch<ExamSessionBatchResult>(`/hr/requisitions/${job.id}/exam-slots/batch`, {
        method: "POST",
        token,
        body,
      });
      onAdded(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add these sessions.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title="Add exam sessions"
      sub="Every day you choose gets every time window, with the same seats and place. Applicants at this exam pick one."
      busy={submitting}
      width={680}
      onClose={onClose}
      footer={
        <>
          <span className="ark-field__hint" style={{ marginRight: "auto" }}>
            {preview.length === 0
              ? "Choose days to see how many sessions this makes."
              : `${toCreate} new ${toCreate === 1 ? "session" : "sessions"}${repeats > 0 ? `, ${repeats} already there` : ""}`}
          </span>
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} disabled={submitting || toCreate === 0}>
            {submitting ? "Adding..." : toCreate > 0 ? `Add ${toCreate} ${toCreate === 1 ? "Session" : "Sessions"}` : "Add Sessions"}
          </Button>
        </>
      }
    >
      <div className="ark-fields">
        {examStages.length > 1 && (
          <label className="ark-field">
            <span className="ark-field__label">Examination</span>
            <select className="ark-input" value={stage} onChange={(e) => setStage(e.target.value)}>
              {examStages.map((s) => (
                <option key={s} value={s}>
                  {jobStageLabel(s, job)}
                </option>
              ))}
            </select>
          </label>
        )}

        <div className="ark-field">
          <div className="ark-field__label-row">
            <span className="ark-field__label">Days</span>
            <div className="ark-tabs" role="group" aria-label="How to choose the days">
              <button type="button" className="ark-tab" aria-pressed={mode === "days"} onClick={() => setMode("days")}>
                Pick Days
              </button>
              <button type="button" className="ark-tab" aria-pressed={mode === "range"} onClick={() => setMode("range")}>
                Date Range
              </button>
            </div>
          </div>

          {mode === "days" ? (
            <>
              <CalendarPicker label="Exam days" selected={dates} onPick={toggleDate} isEnabled={(day) => day >= today} />
              {dates.length > 0 ? (
                <div className="ark-chips">
                  {dates.map((day) => (
                    <span key={day} className="ark-chip ark-chip--neutral">
                      {formatDay(day)}
                      <button type="button" className="ark-chip__remove" aria-label={`Remove ${formatDay(day)}`} onClick={() => toggleDate(day)}>
                        <XIcon width={12} height={12} />
                      </button>
                    </span>
                  ))}
                </div>
              ) : (
                <p className="ark-field__hint">Press each day the exam runs.</p>
              )}
            </>
          ) : (
            <div className="ark-session-range">
              <label className="ark-field">
                <span className="ark-field__label">From</span>
                <input type="date" className="ark-input" min={today} value={rangeFrom} onChange={(e) => setRangeFrom(e.target.value)} />
              </label>
              <label className="ark-field">
                <span className="ark-field__label">To</span>
                <input type="date" className="ark-input" min={rangeFrom || today} value={rangeTo} onChange={(e) => setRangeTo(e.target.value)} />
              </label>
              <label className="ark-check">
                <input type="checkbox" checked={weekdaysOnly} onChange={(e) => setWeekdaysOnly(e.target.checked)} />
                Weekdays only
              </label>
              <p className="ark-field__hint ark-session-range__count">
                {rangeFrom && rangeTo
                  ? `${rangeDays.length} ${rangeDays.length === 1 ? "day" : "days"}`
                  : "Choose the first and last day."}
              </p>
            </div>
          )}
        </div>

        <div className="ark-field">
          <span className="ark-field__label">Time windows</span>
          <div className="ark-session-presets">
            {WINDOW_PRESETS.map((preset) => {
              const added = windows.some((w) => w.start === preset.start && w.end === preset.end);
              return (
                <button
                  key={preset.label}
                  type="button"
                  className="ark-preset"
                  aria-pressed={added}
                  onClick={() => (added ? undefined : addPreset(preset.start, preset.end))}
                  disabled={added}
                >
                  <PlusIcon width={12} height={12} aria-hidden="true" />
                  {preset.label} <span className="ark-preset__time">{formatWindow(preset.start, preset.end)}</span>
                </button>
              );
            })}
          </div>
          <div className="ark-windows">
            {windows.map((window, index) => (
              <div key={index} className="ark-window">
                <input
                  type="time"
                  className="ark-input"
                  aria-label={`Window ${index + 1} starts`}
                  value={window.start}
                  onChange={(e) => updateWindow(index, { start: e.target.value })}
                />
                <span className="ark-window__dash">to</span>
                <input
                  type="time"
                  className="ark-input"
                  aria-label={`Window ${index + 1} ends`}
                  value={window.end}
                  onChange={(e) => updateWindow(index, { end: e.target.value })}
                />
                <button
                  type="button"
                  className="ark-icon-btn"
                  aria-label={`Remove window ${index + 1}`}
                  onClick={() => setWindows((prev) => prev.filter((_, i) => i !== index))}
                >
                  <XIcon width={14} height={14} />
                </button>
              </div>
            ))}
          </div>
          {windows.length < 6 && (
            <div>
              <Button variant="ghost" size="sm" onClick={() => setWindows((prev) => [...prev, { start: "", end: "" }])}>
                <PlusIcon width={14} height={14} /> Add a Custom Window
              </Button>
            </div>
          )}
        </div>

        <div className="ark-fields ark-fields--2">
          <label className="ark-field">
            <span className="ark-field__label">Seats per session</span>
            <input
              type="number"
              min={1}
              max={500}
              className="ark-input"
              placeholder="e.g. 30"
              value={seats}
              onChange={(e) => setSeats(e.target.value)}
            />
          </label>
          <label className="ark-field">
            <span className="ark-field__label">Location</span>
            <input
              type="text"
              className="ark-input"
              placeholder="e.g. MSEUF Lucena Campus, Room 204"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
            />
          </label>
        </div>

        {preview.length > 0 && windowProblem(windows) === null && (
          <div className="ark-field">
            <span className="ark-field__label">What this makes</span>
            <ul className="ark-session-preview">
              {preview.map((p) => (
                <li key={`${p.date}|${p.start}`} data-exists={p.exists || undefined}>
                  <span className="ark-session-preview__when">
                    {formatDay(p.date)} · {formatWindow(p.start, p.end)}
                  </span>
                  {p.exists && <span className="ark-session-preview__note">Already there, skipped</span>}
                </li>
              ))}
            </ul>
          </div>
        )}

        {error && <p className="ark-form-error">{error}</p>}
      </div>
    </Modal>
  );
}
