/**
 * The Candidate Profile's Examinations tab: one card per examination
 * stage, with where the applicant's exam session stands and the score
 * recorded afterwards.
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import type {
  CandidateProfile,
  ExamSessionBatchResult,
  ExamSlot,
  ExaminationEntry,
  RequisitionDetail,
} from "../../../../../../shared/api/pipeline";
import { apiFetch } from "../../../../../../shared/api/client";
import { formatClock, formatDay, formatWindow, todayInPhilippines } from "../../../../../../shared/lib/scheduleTime";
import { isExamStage } from "../../../../../../shared/lib/stageLabels";
import { Button } from "../../../../../../shared/ui/Button";
import { AlertIcon } from "../../../../../../shared/ui/icons";
import { AddExamSessionsDialog } from "../../../components/AddExamSessionsDialog";
import { BookExamSessionDialog } from "../../../components/BookExamSessionDialog";
import { EXAM_SESSIONS_ANCHOR } from "../../../components/ExamSessionsPanel";
import { addedSummary } from "../../../../model/examSessions";
import { Pending } from "../atoms";
import { capitalize } from "../display";
import type { ExamBookingResolver, ExamScoreEditor } from "../types";
import { Tag } from "../../../../../../shared/ui/Tag";

interface ExaminationsTabProps {
  profile: CandidateProfile;
  job: RequisitionDetail | null;
  token: string | null;
  examStageKeys: string[];
  scoreEditor: ExamScoreEditor;
  bookingResolver: ExamBookingResolver;
  /** The profile after HR booked or moved the applicant. */
  onProfile: (profile: CandidateProfile) => void;
  /** Re-reads the profile, e.g. after sessions were added. */
  onReload: () => void;
}

/** What "Taken on" starts at: the date already recorded, else the booked
 *  session's date once it has come, else today. Never a future date:
 *  the server refuses one. */
function defaultTakenOn(recorded: string | null | undefined, booked: string | undefined): string {
  if (recorded) return recorded;
  const today = todayInPhilippines();
  return booked && booked <= today ? booked : today;
}

function firstName(full: string): string {
  return full.trim().split(/\s+/)[0] || full;
}

/** Exams are face to face, so the score is entered by hand, with the day
 * it was taken; a slot still waiting from the old Pre-Screening flow shows
 * too. A session is the only way an exam gets a time: the applicant picks
 * one of the job's sessions, or HR books one here. The score editor's
 * state stays on the page (see ../types.ts); the session dialogs are
 * short-lived and live here. */
export function ExaminationsTab({
  profile,
  job,
  token,
  examStageKeys,
  scoreEditor,
  bookingResolver,
  onProfile,
  onReload,
}: ExaminationsTabProps) {
  const [booking, setBooking] = useState<{ stage: string; currentSlotId: number | null } | null>(null);
  const [adding, setAdding] = useState<string | null>(null);
  const [existing, setExisting] = useState<ExamSlot[]>([]);
  const [notice, setNotice] = useState<string | null>(null);

  async function openAdd(stage: string) {
    setNotice(null);
    // the job's sessions so far, so the preview can mark repeats
    try {
      setExisting(await apiFetch<ExamSlot[]>(`/hr/requisitions/${profile.requisition_id}/exam-slots`, { token }));
    } catch {
      setExisting([]);
    }
    setAdding(stage);
  }

  const examStages = job ? job.workflow_definition.filter(isExamStage) : examStageKeys;
  const sessionsHref = `/hr/job-openings/${profile.requisition_id}#${EXAM_SESSIONS_ANCHOR}`;

  return (
    <div className="ark-interviews">
      {examStageKeys.length === 0 && <Pending />}
      {notice && (
        <p className="ark-session-notice" role="status">
          {notice}
        </p>
      )}
      {examStageKeys.map((stageType) => {
        const entry = profile.examinations[stageType];
        // nothing to book into yet: adding sessions is the next step
        const needsSessions = !entry.schedule && entry.open_sessions === 0;
        const over = entry.status === "complete" || entry.status === "skipped";
        return (
          <article key={stageType} className="ark-stagecard">
            <header className="ark-stagecard__head">
              <div className="ark-stagecard__who">
                <h3 className="ark-stagecard__round">{entry.label}</h3>
                <div className="ark-stagecard__meta">
                  <SessionLine entry={entry} applicantName={profile.applicant_name} />
                </div>
              </div>
              <div className="ark-stagecard__marks">
                <Tag dot>{capitalize(entry.status)}</Tag>
                {entry.score != null && <Tag tone="blue">{entry.score} / 100</Tag>}
              </div>
            </header>

            {entry.pending_booking && <LegacyProposal entry={entry} bookingResolver={bookingResolver} />}

            <footer className="ark-stagecard__admin">
              {entry.none_work && (
                <div className="ark-stagecard__request">
                  <AlertIcon width={16} height={16} aria-hidden="true" style={{ color: "var(--warning-text)", flexShrink: 0, marginTop: 2 }} />
                  <div>
                    <div className="ark-stagecard__request-title">
                      None of the sessions work for {firstName(profile.applicant_name)}
                    </div>
                    <p className="ark-stagecard__request-text">
                      {entry.none_work.note ? `"${entry.none_work.note}"` : "No reason given."} Adding sessions tells them
                      at once.
                    </p>
                  </div>
                </div>
              )}

              <div className="ark-stagecard__admin-row">
                <span>
                  <span className="ark-stagecard__admin-label">Session</span>
                  <Link to={sessionsHref} className="ark-stagecard__link">
                    Manage all sessions
                  </Link>
                </span>
                <span className="ark-stagecard__actions">
                  <Button variant={needsSessions && !over ? "primary" : "secondary"} size="sm" onClick={() => openAdd(stageType)}>
                    Add Sessions
                  </Button>
                  {!needsSessions && (
                    <Button
                      variant={entry.schedule ? "secondary" : "primary"}
                      size="sm"
                      disabled={over}
                      onClick={() => setBooking({ stage: stageType, currentSlotId: entry.booked_slot_id })}
                    >
                      {entry.schedule_source === "session"
                        ? "Move to Another Session"
                        : entry.schedule_source === "typed"
                        ? "Move to a Session"
                        : "Book a Session for Them"}
                    </Button>
                  )}
                </span>
              </div>

              <ScoreRow
                stageType={stageType}
                entry={entry}
                scoreEditor={scoreEditor}
                onOpen={() => {
                  scoreEditor.setEditingStage(stageType);
                  scoreEditor.setInput(entry.score != null ? String(entry.score) : "");
                  scoreEditor.setTakenOn(defaultTakenOn(entry.taken_on, entry.schedule?.date));
                  scoreEditor.setError(null);
                }}
              />
            </footer>
          </article>
        );
      })}

      {booking && (
        <BookExamSessionDialog
          open
          applicationId={profile.application_id}
          applicantName={profile.applicant_name}
          requisitionId={profile.requisition_id}
          stageType={booking.stage}
          stageLabel={profile.examinations[booking.stage]?.label ?? "Examination"}
          currentSlotId={booking.currentSlotId}
          token={token}
          onClose={() => setBooking(null)}
          onBooked={(updated) => {
            setBooking(null);
            setNotice(`${firstName(profile.applicant_name)} is booked and has been told.`);
            onProfile(updated);
          }}
        />
      )}

      {job && adding && (
        <AddExamSessionsDialog
          open
          job={job}
          examStages={examStages}
          initialStage={adding}
          existing={existing}
          token={token}
          onClose={() => setAdding(null)}
          onAdded={(result: ExamSessionBatchResult) => {
            setAdding(null);
            setNotice(addedSummary(result));
            onReload();
          }}
        />
      )}
    </div>
  );
}

/** Where this exam's session stands, in one line. */
function SessionLine({ entry, applicantName }: { entry: ExaminationEntry; applicantName: string }) {
  const name = firstName(applicantName);
  const schedule = entry.schedule;
  if (schedule && entry.schedule_source === "session") {
    return (
      <>
        <span className="ark-stagecard__name">Booked</span>
        <span className="ark-stagecard__when">
          {formatDay(schedule.date)} · {formatWindow(schedule.time, schedule.end_time)} · {schedule.location}
        </span>
        <span className="ark-stagecard__when">
          {entry.applicant_can_change ? `${name} can change it until 24 hours before` : "Only HR can move it now"}
        </span>
      </>
    );
  }
  if (schedule) {
    return (
      <>
        <span className="ark-stagecard__name">Set by hand</span>
        <span className="ark-stagecard__when">
          {formatDay(schedule.date)} · {formatClock(schedule.time)} · {schedule.location}
        </span>
      </>
    );
  }
  if (entry.open_sessions === 0) return <span>No sessions open for this exam yet</span>;
  return (
    <>
      <span className="ark-stagecard__name">{entry.status === "pending" ? "Not at this exam yet" : `Waiting for ${name} to pick`}</span>
      <span className="ark-stagecard__when">
        {entry.open_sessions} {entry.open_sessions === 1 ? "session" : "sessions"} open
      </span>
    </>
  );
}

/** The score and the day the exam was taken. */
function ScoreRow({
  stageType,
  entry,
  scoreEditor,
  onOpen,
}: {
  stageType: string;
  entry: ExaminationEntry;
  scoreEditor: ExamScoreEditor;
  onOpen: () => void;
}) {
  const editing = scoreEditor.editingStage === stageType;
  return (
    <>
      <div className="ark-stagecard__admin-row">
        <span>
          <span className="ark-stagecard__admin-label">Result</span>
          {entry.score != null
            ? `${entry.score} / 100${entry.taken_on ? `, taken ${formatDay(entry.taken_on)}` : ""}`
            : "Enter it here once the exam has been marked. It's sat outside ARKIVE."}
        </span>
        {!editing && (
          <Button variant="secondary" size="sm" onClick={onOpen}>
            {entry.score != null ? "Update Score" : "Enter Score"}
          </Button>
        )}
      </div>
      {editing && (
        <div className="ark-stagecard__editor ark-score-editor">
          <label className="ark-field">
            <span className="ark-field__label">Score</span>
            <input
              type="number"
              min={0}
              max={100}
              step={0.1}
              className="ark-input"
              value={scoreEditor.input}
              onChange={(e) => scoreEditor.setInput(e.target.value)}
              placeholder="0 to 100"
            />
          </label>
          <label className="ark-field">
            <span className="ark-field__label">Taken on</span>
            <input
              type="date"
              className="ark-input"
              max={todayInPhilippines()}
              value={scoreEditor.takenOn}
              onChange={(e) => scoreEditor.setTakenOn(e.target.value)}
            />
          </label>
          <div className="ark-score-editor__actions">
            <Button variant="primary" size="sm" onClick={() => scoreEditor.submit(stageType)} disabled={scoreEditor.submitting}>
              {scoreEditor.submitting ? "Saving..." : "Save Score"}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => scoreEditor.setEditingStage(null)} disabled={scoreEditor.submitting}>
              Cancel
            </Button>
          </div>
          {scoreEditor.error && <p className="ark-stagecard__error">{scoreEditor.error}</p>}
        </div>
      )}
    </>
  );
}

/** A slot the Exam Scheduling agent proposed under the old Pre-Screening
 *  flow, still waiting for HR. No new ones are made; this stays only
 *  while old ones are pending. */
function LegacyProposal({ entry, bookingResolver }: { entry: ExaminationEntry; bookingResolver: ExamBookingResolver }) {
  const pending = entry.pending_booking!;
  const chosen = bookingResolver.slotOverride[pending.id] ?? pending.proposed_slot_id;
  const busy = bookingResolver.resolvingId === pending.id;
  return (
    <div className="ark-stagecard__admin">
      <div className="ark-stagecard__request">
        <AlertIcon width={16} height={16} aria-hidden="true" style={{ color: "var(--warning-text)", flexShrink: 0, marginTop: 2 }} />
        <div style={{ flex: 1 }}>
          <div className="ark-stagecard__request-title">A proposed slot from the old Pre-Screening flow</div>
          <p className="ark-stagecard__request-text">
            From the applicant's {pending.candidate_slots.length} selected {pending.candidate_slots.length === 1 ? "slot" : "slots"}:
          </p>
          <select
            className="ark-input"
            value={chosen}
            onChange={(e) => bookingResolver.setSlotOverride((prev) => ({ ...prev, [pending.id]: Number(e.target.value) }))}
            style={{ marginTop: 8 }}
          >
            {pending.candidate_slots.map((slot) => (
              <option key={slot.id} value={slot.id}>
                {formatDay(slot.date)}, {formatClock(slot.time)} at {slot.location}
                {slot.id === pending.proposed_slot_id ? " (proposed)" : ""}
              </option>
            ))}
          </select>
          <div className="ark-stagecard__actions" style={{ marginTop: 10 }}>
            <Button variant="primary" size="sm" disabled={busy} onClick={() => bookingResolver.resolve(pending.id, "approve", chosen)}>
              Approve
            </Button>
            <Button variant="outline" size="sm" disabled={busy} onClick={() => bookingResolver.resolve(pending.id, "deny")}>
              Deny
            </Button>
          </div>
          {bookingResolver.error && <p className="ark-stagecard__error">{bookingResolver.error}</p>}
        </div>
      </div>
    </div>
  );
}
