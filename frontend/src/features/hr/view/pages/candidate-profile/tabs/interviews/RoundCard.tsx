/** One interview round, conclusion first: who evaluated and what they
 *  concluded, then the summary, with the feedback itself behind a toggle. */

import { useId } from "react";
import { Link } from "react-router-dom";
import { ScorecardAreas } from "../../../../../../../shared/components/ScorecardReadOnly";
import { Avatar } from "../../../../../../../shared/ui/Avatar";
import { Button } from "../../../../../../../shared/ui/Button";
import { AlertIcon, ChevronDownIcon, SparklesIcon } from "../../../../../../../shared/ui/icons";
import {
  RECOMMENDATION_OPTIONS,
  SCORECARD_ITEM_CODES,
  TIER_COPY,
  type EvaluatorRecommendation,
} from "../../../../../../../shared/lib/scorecard";
import type { EvaluatorAssignment, RescheduleResolver, ScheduleEditor, SlotSender } from "../../types";
import { scheduleInputStyle } from "../../display";
import type { InterviewRatingEntry } from "../../../../../../../shared/api/pipeline";
import { shownText } from "../../../../../../../shared/lib/displayText";
import { minTimeFor, todayInPhilippines } from "../../../../../../../shared/lib/scheduleTime";
import { Tag } from "../../../../../../../shared/ui/Tag";
import { recommendationTone, tierTone } from "../../../../../../../shared/lib/statusTags";
import type { TagTone } from "../../../../../../../shared/ui/Tag";
import { TimesRow } from "./RoundTimes";

/** Pass/fail colour, as on the verdict: the band's words carry the
 * nuance, the colour only which side of the line it falls. */
const RECOMMENDATION_LABEL = Object.fromEntries(RECOMMENDATION_OPTIONS.map((o) => [o.value, o.label])) as Record<
  EvaluatorRecommendation,
  string
>;

export function RoundCard({
  stageType,
  entry,
  requisitionId,
  open,
  onToggle,
  scheduleEditor,
  assignment,
  reschedule,
  slotSender,
}: {
  stageType: string;
  entry: InterviewRatingEntry;
  requisitionId: number;
  open: boolean;
  onToggle: () => void;
  scheduleEditor: ScheduleEditor;
  assignment: EvaluatorAssignment;
  reschedule: RescheduleResolver;
  slotSender: SlotSender;
}) {
  const drawerId = useId();
  const evaluated = entry.computed_score != null && entry.tier != null && entry.item_ratings != null;
  const evaluator = entry.assigned_evaluator_name;
  // With no AI summary (the agent was unavailable when it was submitted),
  // the evaluator's own remarks are the summary — shown up top, not twice.
  const summary = entry.ai_summary != null ? shownText(entry.ai_summary) : entry.remarks;
  const summaryIsRemarks = !entry.ai_summary && !!entry.remarks;
  const ratedCount = evaluated ? SCORECARD_ITEM_CODES.filter((c) => entry.item_ratings![c] != null).length : 0;

  return (
    <article className="ark-interview" data-state={evaluated ? "done" : "pending"}>
      <header className="ark-interview__head">
        <div className="ark-interview__who">
          <h3 className="ark-interview__round">{entry.label}</h3>
          <div className="ark-interview__meta">
            {evaluator ? (
              <>
                <Avatar name={evaluator} size={22} src={entry.assigned_evaluator_avatar_url} />
                <span className="ark-interview__name">{evaluator}</span>
              </>
            ) : (
              <span>No evaluator assigned yet</span>
            )}
            {evaluated && entry.submitted_at && (
              <span className="ark-interview__when">
                Submitted{" "}
                {new Date(entry.submitted_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
              </span>
            )}
          </div>
        </div>
        <div className="ark-interview__marks">
          {evaluated ? (
            <>
              <span className="ark-interview__score">
                {entry.computed_score!.toFixed(1)}
                <small> / 5</small>
              </span>
              <Tag tone={tierTone(entry.tier)}>{TIER_COPY[entry.tier!].label}</Tag>
              {entry.recommendation && (
                <Tag tone={recommendationTone(entry.recommendation)} title="The evaluator's own recommendation">
                  {RECOMMENDATION_LABEL[entry.recommendation]}
                </Tag>
              )}
            </>
          ) : (
            <Tag dot>Awaiting evaluation</Tag>
          )}
        </div>
      </header>

      {evaluated ? (
        <>
          {summary && (
            <div className="ark-interview__summary">
              <div className="ark-interview__summary-head">
                <span className="ark-interview__summary-label">
                  {summaryIsRemarks ? (
                    "Evaluator's remarks"
                  ) : (
                    <>
                      <SparklesIcon width={14} height={14} aria-hidden="true" />
                      Interview summary
                    </>
                  )}
                </span>
                {entry.rubric_coverage_score != null && (
                  <span className="ark-interview__coverage">
                    Rubric coverage <strong>{entry.rubric_coverage_score.toFixed(0)}</strong> / 100
                  </span>
                )}
              </div>
              <p className="ark-interview__summary-text">{summary}</p>
            </div>
          )}

          <button
            type="button"
            className="ark-interview__toggle"
            aria-expanded={open}
            aria-controls={drawerId}
            onClick={onToggle}
          >
            <ChevronDownIcon width={15} height={15} aria-hidden="true" />
            <span className="ark-interview__toggle-label">
              {open ? "Hide" : "View"} {evaluator ? `${evaluator.split(" ")[0]}'s` : "the evaluator's"} feedback
            </span>
            <span className="ark-interview__toggle-meta">
              {!summaryIsRemarks && entry.remarks ? "Remarks · " : ""}
              {ratedCount} ratings across 4 areas
            </span>
          </button>
          <div className="ark-drawer" id={drawerId} data-open={open || undefined}>
            <div>
              <div className="ark-interview__feedback">
                {!summaryIsRemarks && entry.remarks && (
                  <figure className="ark-interview__remarks">
                    <figcaption>Evaluator's remarks</figcaption>
                    <blockquote>{entry.remarks}</blockquote>
                  </figure>
                )}
                <ScorecardAreas itemRatings={entry.item_ratings!} />
              </div>
            </div>
          </div>
        </>
      ) : (
        <p className="ark-interview__pending">
          {evaluator ? `${evaluator} hasn't submitted feedback yet.` : "Assign an evaluator to this round below."}
        </p>
      )}

      <footer className="ark-interview__admin">
        <div className="ark-interview__admin-row">
          <span>
            <span className="ark-interview__admin-label">Evaluator</span>
            {assignment.pool.length === 0 ? "This job has no evaluator pool yet: " : "Only this job's evaluator pool can be assigned: "}
            <Link to={`/hr/requisitions/${requisitionId}/workflow`} className="ark-interview__link">
              {assignment.pool.length === 0 ? "add evaluators in the Workflow Builder" : "add more in the Workflow Builder"}
            </Link>
            .
          </span>
          <select
            value={entry.assigned_evaluator_id ?? ""}
            disabled={assignment.assigningStage === stageType}
            onChange={(e) => assignment.assign(stageType, e.target.value ? Number(e.target.value) : null)}
            style={{ ...scheduleInputStyle, width: 220 }}
            aria-label={`Evaluator for ${entry.label}`}
          >
            <option value="">Unassigned</option>
            {/* A deactivated evaluator stays listed (they may already be the
                one assigned) but can't be picked for a new interview. */}
            {assignment.pool.map((member) => (
              <option key={member.evaluator_id} value={member.evaluator_id} disabled={!member.is_active}>
                {member.full_name}
                {member.is_active ? "" : " (deactivated)"}
              </option>
            ))}
          </select>
        </div>
        {entry.assigned_evaluator_id != null &&
          assignment.pool.some((m) => m.evaluator_id === entry.assigned_evaluator_id && !m.is_active) &&
          !evaluated && (
            <p className="ark-interview__error">
              This evaluator's account is deactivated, so they can't conduct this interview. Pick someone else.
            </p>
          )}
        {assignment.error && assignment.error.stage === stageType && (
          <p className="ark-interview__error">{assignment.error.message}</p>
        )}

        {!evaluated && <TimesRow stageType={stageType} entry={entry} slotSender={slotSender} />}

        {entry.reschedule_request && (
          <div className="ark-interview__request">
            <AlertIcon width={16} height={16} style={{ color: "var(--warning-text)", flexShrink: 0, marginTop: 2 }} />
            <div style={{ flex: 1 }}>
              <div className="ark-interview__request-title">Reschedule requested</div>
              <p className="ark-interview__request-text">
                Proposed: {entry.reschedule_request.proposed_date} at {entry.reschedule_request.proposed_time}
                {entry.reschedule_request.reason && ` ("${entry.reschedule_request.reason}")`}
              </p>
              <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                <Button
                  variant="primary"
                  disabled={reschedule.resolvingId === entry.reschedule_request.id}
                  onClick={() =>
                    reschedule.resolve(
                      entry.reschedule_request!.id,
                      "approve",
                      entry.reschedule_request!.proposed_date,
                      entry.reschedule_request!.proposed_time
                    )
                  }
                  style={{ padding: "6px 12px", fontSize: "var(--text-sm)" }}
                >
                  Accept Proposed Time
                </Button>
                <Button
                  variant="outline"
                  disabled={reschedule.resolvingId === entry.reschedule_request.id}
                  onClick={() => reschedule.resolve(entry.reschedule_request!.id, "deny")}
                  style={{ padding: "6px 12px", fontSize: "var(--text-sm)" }}
                >
                  Deny
                </Button>
              </div>
              {reschedule.error && <p className="ark-interview__error">{reschedule.error}</p>}
            </div>
          </div>
        )}

        {scheduleEditor.editingStage === stageType ? (
          <div className="ark-interview__editor">
            <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
              <Button
                type="button"
                variant={scheduleEditor.mode === "in_person" ? "primary" : "outline"}
                onClick={() => scheduleEditor.setMode("in_person")}
                style={{ padding: "6px 12px", fontSize: "var(--text-sm)" }}
              >
                In-Person
              </Button>
              <Button
                type="button"
                variant={scheduleEditor.mode === "online" ? "primary" : "outline"}
                onClick={() => scheduleEditor.setMode("online")}
                style={{ padding: "6px 12px", fontSize: "var(--text-sm)" }}
              >
                Online
              </Button>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                type="date"
                min={todayInPhilippines()}
                value={scheduleEditor.date}
                onChange={(e) => scheduleEditor.setDate(e.target.value)}
                style={scheduleInputStyle}
              />
              <input
                type="time"
                min={minTimeFor(scheduleEditor.date)}
                value={scheduleEditor.time}
                onChange={(e) => scheduleEditor.setTime(e.target.value)}
                style={scheduleInputStyle}
              />
            </div>
            {scheduleEditor.mode === "in_person" ? (
              <input
                type="text"
                placeholder="e.g. MSEUF Lucena Campus, Room 204"
                value={scheduleEditor.location}
                onChange={(e) => scheduleEditor.setLocation(e.target.value)}
                style={{ ...scheduleInputStyle, width: "100%", marginTop: 8, boxSizing: "border-box" }}
              />
            ) : (
              <input
                type="url"
                placeholder="e.g. https://meet.google.com/xxx-xxxx-xxx"
                value={scheduleEditor.meetingLink}
                onChange={(e) => scheduleEditor.setMeetingLink(e.target.value)}
                style={{ ...scheduleInputStyle, width: "100%", marginTop: 8, boxSizing: "border-box" }}
              />
            )}
            {scheduleEditor.error && <p className="ark-interview__error">{scheduleEditor.error}</p>}
            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
              <Button variant="primary" onClick={scheduleEditor.submit} disabled={scheduleEditor.submitting} style={{ padding: "8px 16px" }}>
                {scheduleEditor.submitting ? "Saving..." : "Save Schedule"}
              </Button>
              <Button
                variant="ghost"
                onClick={() => scheduleEditor.setEditingStage(null)}
                disabled={scheduleEditor.submitting}
                style={{ padding: "8px 16px" }}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="ark-interview__admin-row">
            <span>
              <span className="ark-interview__admin-label">Schedule</span>
              {entry.schedule ? (
                <>
                  {entry.schedule.date} at {entry.schedule.time}
                  {entry.schedule.end_time ? `–${entry.schedule.end_time}` : ""} ·{" "}
                  {entry.schedule.mode === "online" ? (
                    <>
                      Online:{" "}
                      <a href={entry.schedule.meeting_link ?? undefined} target="_blank" rel="noreferrer" className="ark-interview__link">
                        {entry.schedule.meeting_link}
                      </a>
                    </>
                  ) : (
                    entry.schedule.location
                  )}
                  <ConfirmationPill confirmation={entry.schedule_confirmation} />
                </>
              ) : (
                "Not yet scheduled."
              )}
            </span>
            <Button variant="secondary" onClick={() => scheduleEditor.open(stageType)} style={{ padding: "6px 12px", fontSize: "var(--text-sm)" }}>
              {entry.schedule ? "Edit Schedule" : "Set Schedule"}
            </Button>
          </div>
        )}
      </footer>
    </article>
  );
}

/** Where the applicant stands on the booked time. Nothing for a time
 *  booked before confirmations existed. */
function ConfirmationPill({ confirmation }: { confirmation: InterviewRatingEntry["schedule_confirmation"] }) {
  if (!confirmation) return null;
  const [tone, label]: [TagTone, string] =
    confirmation.response === "confirmed"
      ? ["green", "Confirmed"]
      : confirmation.response === "unavailable"
        ? ["amber", "Applicant not available"]
        : ["neutral", "Awaiting applicant's confirmation"];
  return (
    <Tag tone={tone} dot className="ark-interview__confirmation" title={confirmation.note ?? undefined}>
      {label}
    </Tag>
  );
}
