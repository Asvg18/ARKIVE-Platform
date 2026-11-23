import { useState } from "react";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { ApplicationDetail, ScheduleConfirmation } from "../../../../shared/api/applicant";
import { formatClock, formatDay, formatWindow } from "../../../../shared/lib/scheduleTime";
import { isExamStage } from "../../../../shared/lib/stageLabels";
import { Button } from "../../../../shared/ui/Button";
import { AlertIcon, CalendarIcon, CheckIcon, ClockIcon, MapPinIcon, VideoIcon } from "../../../../shared/ui/icons";
import { ExamSessionPicker } from "./ExamSessionPicker";
import { InterviewSlotPicker } from "./InterviewSlotPicker";

interface ScheduleInfo {
  date: string;
  time: string;
  /** The session's end, when the applicant booked an exam session. */
  end_time?: string | null;
  location?: string;
  mode?: "in_person" | "online";
  meeting_link?: string | null;
}

/** Scheduler display for the Examination and the Final Interview rounds.
 *
 * An unscheduled examination is where the applicant books one of the
 * job's exam sessions (ExamSessionPicker), and an unbooked interview is
 * where they pick from the times HR sent (InterviewSlotPicker). For an
 * interview HR set by hand, what the applicant gets is the one thing only
 * they know: whether they can actually be there. That way a clash is
 * known before the day, and a candidate who cannot make a Tuesday morning
 * is not mistaken for one who has lost interest.
 *
 * Saying "not available" does not withdraw anything. It tells HR, who
 * rearrange. Interviews only: a booked exam session is changed by
 * picking another one instead (until 24 hours before it starts).
 *
 * Scheduling still never advances the DFA itself; the stage moves on once
 * HR (or, for interviews, the evaluator) processes the outcome. */
export function ScheduleScreen({
  application,
  token,
  onUpdate,
}: {
  application: ApplicationDetail;
  token?: string | null;
  onUpdate?: (updated: ApplicationDetail) => void;
}) {
  const currentInstance = application.stage_instances.find(
    (s) => s.stage_type === application.current_stage
  );
  const schedule = currentInstance?.payload?.schedule as ScheduleInfo | undefined;
  const confirmation = currentInstance?.payload?.schedule_confirmation as
    | ScheduleConfirmation
    | undefined;
  const stageName = currentInstance?.label ?? application.current_stage ?? "–";
  const isOnline = schedule?.mode === "online";
  const isExam = isExamStage(application.current_stage);
  const examBooking =
    isExam && application.exam_booking?.stage_type === application.current_stage ? application.exam_booking : null;
  const [changing, setChanging] = useState(false);

  const slotOffer = application.interview_slot_offer;
  if (!schedule && slotOffer && slotOffer.stage_type === application.current_stage && onUpdate) {
    return (
      <InterviewSlotPicker
        application={application}
        offer={slotOffer}
        stageName={stageName}
        token={token ?? null}
        onUpdate={onUpdate}
      />
    );
  }

  if (isExam && application.current_stage && onUpdate && (!schedule || (changing && examBooking))) {
    return (
      <ExamSessionPicker
        application={application}
        stageType={application.current_stage}
        stageName={stageName}
        token={token ?? null}
        changing={changing && examBooking ? examBooking : undefined}
        onCancelChange={() => setChanging(false)}
        onUpdate={(updated) => {
          setChanging(false);
          onUpdate(updated);
        }}
      />
    );
  }

  return (
    <div>
      <h2 style={heading}>{stageName}</h2>
      {schedule ? (
        <>
          <p style={subtext}>
            {isExam ? "Your examination is booked:" : schedule.end_time ? "Your interview is booked:" : "HR has scheduled this stage:"}
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 16 }}>
            <InfoRow icon={<CalendarIcon width={16} height={16} />} label="Date" value={formatDay(schedule.date)} />
            <InfoRow
              icon={<ClockIcon width={16} height={16} />}
              label="Time"
              value={schedule.end_time ? formatWindow(schedule.time, schedule.end_time) : formatClock(schedule.time)}
            />
            {isOnline ? (
              <InfoRow
                icon={<VideoIcon width={16} height={16} />}
                label="Meeting Link"
                value={schedule.meeting_link ?? ""}
                href={schedule.meeting_link ?? undefined}
              />
            ) : (
              <InfoRow icon={<MapPinIcon width={16} height={16} />} label="Location" value={schedule.location ?? ""} />
            )}
          </div>
          {confirmation && token && onUpdate && application.current_stage ? (
            <ConfirmAvailability
              application={application}
              stageType={application.current_stage}
              confirmation={confirmation}
              token={token}
              onUpdate={onUpdate}
            />
          ) : examBooking ? (
            <div className="ark-stage-actions">
              {examBooking.can_change ? (
                <>
                  <Button variant="secondary" onClick={() => setChanging(true)}>
                    Change Session
                  </Button>
                  <span className="ark-stage-hint">You can change it here until 24 hours before it starts.</span>
                </>
              ) : (
                <span className="ark-stage-hint">
                  It starts in less than 24 hours, so it can no longer be changed here. To move it, contact the HR office.
                </span>
              )}
            </div>
          ) : (
            <p style={{ ...subtext, marginTop: 16 }}>HR will advance your application once this has taken place.</p>
          )}
        </>
      ) : (
        <p style={subtext}>
          Not scheduled yet. HR will post the date, time and {isExam ? "location" : "location or meeting link"} here once it's set.
        </p>
      )}
    </div>
  );
}

/** The one decision on this screen. Answered once per scheduling -- if HR
 *  moves the date, the question is asked again, because a yes against the
 *  old slot says nothing about the new one. */
function ConfirmAvailability({
  application,
  stageType,
  confirmation,
  token,
  onUpdate,
}: {
  application: ApplicationDetail;
  stageType: string;
  confirmation: ScheduleConfirmation;
  token: string | null;
  onUpdate: (updated: ApplicationDetail) => void;
}) {
  const [note, setNote] = useState("");
  const [askingWhy, setAskingWhy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function answer(response: "confirmed" | "unavailable") {
    setSubmitting(true);
    setError(null);
    try {
      const updated = await apiFetch<ApplicationDetail>(
        `/applicant/applications/${application.id}/schedule-confirmation`,
        { method: "POST", token, body: { stage_type: stageType, response, note } }
      );
      onUpdate(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not record your answer. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (confirmation.response === "confirmed") {
    return (
      <div style={{ ...answered, background: "var(--success-bg)", borderLeft: "3px solid var(--success-text)" }}>
        <CheckIcon width={18} height={18} style={{ color: "var(--success-text)", flexShrink: 0, marginTop: 1 }} />
        <span style={answeredText}>
          You've confirmed you're available. Nothing more to do. See you then.
        </span>
      </div>
    );
  }

  if (confirmation.response === "unavailable") {
    return (
      <div style={{ ...answered, background: "var(--warning-bg)", borderLeft: "3px solid var(--warning-text)" }}>
        <AlertIcon width={18} height={18} style={{ color: "var(--warning-text)", flexShrink: 0, marginTop: 1 }} />
        <span style={answeredText}>
          You've told HR you aren't available at this time. Your application is still open. They'll be in
          touch with another.
        </span>
      </div>
    );
  }

  return (
    <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--surface-border)" }}>
      <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", fontWeight: 650, color: "var(--ink-900)", margin: 0 }}>
        Are you available at this time?
      </p>
      <p style={{ ...subtext, marginTop: 4 }}>
        Let HR know either way. Saying you aren't available does not withdraw your application. They'll
        arrange another time.
      </p>

      {askingWhy ? (
        <>
          <textarea
            rows={3}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Optional: anything that helps them pick a better time."
            style={{
              display: "block",
              width: "100%",
              boxSizing: "border-box",
              marginTop: 12,
              padding: "8px 10px",
              border: "1px solid var(--surface-border)",
              borderRadius: "var(--radius)",
              fontFamily: "var(--arkive-font)",
              fontSize: "var(--text-base)",
              color: "var(--ink-900)",
              background: "var(--surface)",
              resize: "vertical",
            }}
          />
          <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
            <Button variant="primary" disabled={submitting} onClick={() => answer("unavailable")}>
              {submitting ? "Sending..." : "Send to HR"}
            </Button>
            <Button variant="secondary" disabled={submitting} onClick={() => setAskingWhy(false)}>
              Go Back
            </Button>
          </div>
        </>
      ) : (
        <div style={{ display: "flex", gap: 10, marginTop: 14, flexWrap: "wrap" }}>
          <Button variant="primary" disabled={submitting} onClick={() => answer("confirmed")}>
            {submitting ? "Working..." : "Yes, I can attend"}
          </Button>
          <Button variant="outline" disabled={submitting} onClick={() => setAskingWhy(true)}>
            I'm not available
          </Button>
        </div>
      )}

      {error && (
        <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "crimson", marginTop: 12 }}>
          {error}
        </p>
      )}
    </div>
  );
}

const answered: React.CSSProperties = {
  display: "flex",
  gap: 10,
  alignItems: "flex-start",
  marginTop: 20,
  padding: "11px 12px",
  borderRadius: "var(--radius-xs)",
};

const answeredText: React.CSSProperties = {
  fontFamily: "var(--arkive-font)",
  fontSize: "var(--text-sm)",
  color: "var(--ink-900)",
  lineHeight: 1.5,
};

function InfoRow({
  icon,
  label,
  value,
  href,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  href?: string;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: "var(--radius)",
          background: "var(--accent-bg)",
          color: "var(--accent)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        {icon}
      </div>
      <div>
        <div style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-2xs)", fontWeight: 700, color: "var(--ink-600)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
          {label}
        </div>
        {href ? (
          <a href={href} target="_blank" rel="noreferrer" style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", fontWeight: 600, color: "var(--accent)" }}>
            {value}
          </a>
        ) : (
          <div style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", fontWeight: 600, color: "var(--ink-900)" }}>{value}</div>
        )}
      </div>
    </div>
  );
}

const heading: React.CSSProperties = { fontFamily: "var(--arkive-font)", fontSize: "var(--text-xl)", fontWeight: 700, color: "var(--ink-900)", margin: 0 };
const subtext: React.CSSProperties = { fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", marginTop: 6 };
