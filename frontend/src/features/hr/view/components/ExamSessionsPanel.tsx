import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { ExamSlot, RequisitionDetail } from "../../../../shared/api/pipeline";
import { formatDay, formatWindow } from "../../../../shared/lib/scheduleTime";
import { isExamStage, jobStageLabel } from "../../../../shared/lib/stageLabels";
import { Avatar } from "../../../../shared/ui/Avatar";
import { Button } from "../../../../shared/ui/Button";
import { ConfirmDialog } from "../../../../shared/ui/ConfirmDialog";
import { ChevronDownIcon, PencilIcon, PlusIcon, TrashIcon } from "../../../../shared/ui/icons";
import { AddExamSessionsDialog } from "./AddExamSessionsDialog";
import { EditExamSessionDialog } from "./EditExamSessionDialog";
import { addedSummary, hasStarted } from "../../model/examSessions";

/** The anchor a candidate's profile links to ("Manage all sessions"). */
export const EXAM_SESSIONS_ANCHOR = "exam-sessions";

/** A job's exam sessions, on its own page. HR adds them in batches, edits
 *  one (its bookers are told), deletes one nobody booked, and opens each to
 *  see who booked it. Every applicant who reaches the exam picks one with a
 *  free seat.
 *
 *  Only sessions still to come are listed. Hidden for a job with no
 *  examination stage. */
export function ExamSessionsPanel({ job, token }: { job: RequisitionDetail; token: string | null }) {
  const examStages = job.workflow_definition.filter(isExamStage);
  const [sessions, setSessions] = useState<ExamSlot[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<ExamSlot | null>(null);
  const [deleting, setDeleting] = useState<ExamSlot | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [openRosters, setOpenRosters] = useState<Set<number>>(new Set());
  const location = useLocation();
  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (examStages.length === 0) return;
    setError(null);
    apiFetch<ExamSlot[]>(`/hr/requisitions/${job.id}/exam-slots`, { token })
      .then(setSessions)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load the exam sessions."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.id, token, examStages.length]);

  // "Manage all sessions" on a candidate's profile links here with
  // #exam-sessions: once the list has loaded, bring the panel into view.
  useEffect(() => {
    if (sessions != null && location.hash === `#${EXAM_SESSIONS_ANCHOR}`) {
      sectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [sessions, location.hash]);

  if (examStages.length === 0) return null;

  const upcoming = (sessions ?? []).filter((s) => !hasStarted(s));
  const earlier = (sessions ?? []).length - upcoming.length;

  function toggleRoster(id: number) {
    setOpenRosters((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function replace(updated: ExamSlot) {
    setSessions((prev) =>
      (prev ?? []).map((s) => (s.id === updated.id ? updated : s)).sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time))
    );
  }

  async function remove() {
    if (!deleting) return;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await apiFetch(`/hr/requisitions/${job.id}/exam-slots/${deleting.id}`, { method: "DELETE", token });
      setSessions((prev) => (prev ?? []).filter((s) => s.id !== deleting.id));
      setNotice("Session deleted.");
      setDeleting(null);
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : "Could not delete this session.");
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <section ref={sectionRef} id={EXAM_SESSIONS_ANCHOR} className="ark-panel" aria-labelledby="exam-sessions-heading">
      <div className="ark-panel__head">
        <div>
          <h2 id="exam-sessions-heading" className="ark-panel__title">Exam sessions</h2>
          <p className="ark-panel__sub">Everyone who reaches the exam picks one with a free seat.</p>
        </div>
        <span className="ark-panel__count">
          {upcoming.length} {upcoming.length === 1 ? "session" : "sessions"}
        </span>
      </div>
      <div className="ark-panel__body">
        {error && <p className="ark-form-error">{error}</p>}
        {notice && <p className="ark-session-notice" role="status">{notice}</p>}
        {sessions && upcoming.length === 0 && (
          <p className="ark-panel__empty">No sessions coming up. Add some so applicants at the exam can book one.</p>
        )}
        {examStages.map((stage) => {
          const rows = upcoming.filter((s) => s.stage_type === stage);
          if (rows.length === 0) return null;
          return (
            <div key={stage}>
              {examStages.length > 1 && <p className="ark-sessions__group">{jobStageLabel(stage, job)}</p>}
              <ul className="ark-sessions">
                {rows.map((slot) => {
                  const bookedCount = slot.booked.length;
                  const rosterOpen = openRosters.has(slot.id);
                  const rosterId = `roster-${slot.id}`;
                  return (
                    <li key={slot.id} className="ark-session">
                      <div className="ark-session__row">
                        <span className="ark-session__text">
                          <span className="ark-session__when">{formatDay(slot.date)}</span>
                          <span className="ark-session__where">
                            {formatWindow(slot.time, slot.end_time)} · {slot.location}
                          </span>
                        </span>
                        <button
                          type="button"
                          className="ark-session__booked"
                          aria-expanded={rosterOpen}
                          aria-controls={rosterId}
                          disabled={bookedCount === 0}
                          onClick={() => toggleRoster(slot.id)}
                        >
                          <span data-full={slot.remaining_capacity <= 0 || undefined}>
                            {bookedCount} of {slot.capacity} booked
                          </span>
                          {bookedCount > 0 && <ChevronDownIcon width={14} height={14} aria-hidden="true" />}
                        </button>
                        <button
                          type="button"
                          className="ark-icon-btn"
                          aria-label={`Edit the session on ${formatDay(slot.date)}`}
                          title="Edit this session"
                          onClick={() => setEditing(slot)}
                        >
                          <PencilIcon width={15} height={15} />
                        </button>
                        <button
                          type="button"
                          className="ark-icon-btn"
                          disabled={bookedCount > 0}
                          title={bookedCount > 0 ? "Someone has booked this session, so it can't be deleted." : "Delete this session"}
                          aria-label={`Delete the session on ${formatDay(slot.date)}`}
                          onClick={() => {
                            setDeleteError(null);
                            setDeleting(slot);
                          }}
                        >
                          <TrashIcon width={15} height={15} />
                        </button>
                      </div>
                      {rosterOpen && bookedCount > 0 && (
                        <ul id={rosterId} className="ark-roster" aria-label={`Booked for ${formatDay(slot.date)}`}>
                          {slot.booked.map((person) => (
                            <li key={person.application_id}>
                              <Link to={`/hr/applications/${person.application_id}?tab=examinations`} className="ark-roster__person">
                                <Avatar name={person.applicant_name} size={24} src={person.avatar_url} />
                                <span>{person.applicant_name}</span>
                              </Link>
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
        {earlier > 0 && (
          <p className="ark-field__hint" style={{ marginTop: "var(--space-3)" }}>
            {earlier} earlier {earlier === 1 ? "session is" : "sessions are"} not shown.
          </p>
        )}
      </div>
      <div className="ark-panel__foot ark-panel__foot--actions">
        <Button variant="secondary" size="sm" onClick={() => setAdding(true)}>
          <PlusIcon width={14} height={14} /> Add Sessions
        </Button>
      </div>

      <AddExamSessionsDialog
        open={adding}
        job={job}
        examStages={examStages}
        existing={sessions ?? []}
        token={token}
        onClose={() => setAdding(false)}
        onAdded={(result) => {
          setSessions((prev) =>
            [...(prev ?? []), ...result.created].sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time))
          );
          setNotice(addedSummary(result));
          setAdding(false);
        }}
      />

      <EditExamSessionDialog
        session={editing}
        requisitionId={job.id}
        token={token}
        onClose={() => setEditing(null)}
        onSaved={(updated) => {
          replace(updated);
          setNotice(updated.booked.length > 0 ? "Session saved. Everyone booked in it has been told about any change." : "Session saved.");
          setEditing(null);
        }}
      />

      <ConfirmDialog
        open={deleting != null}
        title="Delete this session?"
        description={
          deleting
            ? `${formatDay(deleting.date)}, ${formatWindow(deleting.time, deleting.end_time)} at ${deleting.location}. Nobody has booked it yet.`
            : ""
        }
        confirmLabel="Delete Session"
        confirmVariant="danger"
        confirming={deleteBusy}
        onCancel={() => setDeleting(null)}
        onConfirm={remove}
      >
        {deleteError && <p className="ark-form-error" style={{ marginTop: 12 }}>{deleteError}</p>}
      </ConfirmDialog>
    </section>
  );
}
