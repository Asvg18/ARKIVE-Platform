/** One stage of the journey: its node on the rail, its name and date,
 *  any exam score, and, for the stage they are on, the appointment and
 *  what to do next. */
import type { StageInstance } from "../../../../../shared/api/applicant";
import { Tag } from "../../../../../shared/ui/Tag";
import { CalendarIcon, CheckIcon, ClockIcon, MapPinIcon, VideoIcon } from "../../../../../shared/ui/icons";
import { elapsedSince, font, scheduleOf, shortDate, type ScheduleInfo } from "./journeyModel";

function Node({ stage, index, closed }: { stage: StageInstance; index: number; closed: boolean }) {
  const done = stage.status === "complete";
  // a closed application has no live stage -- its instances still say
  // in_progress (status is decoupled from the DFA), but a hired
  // applicant with a pulsing "in progress" marker contradicts the
  // outcome printed directly above it
  const active = stage.status === "in_progress" && !closed;
  const skipped = stage.status === "skipped";

  return (
    <div
      style={{
        width: 26,
        height: 26,
        borderRadius: "50%",
        flexShrink: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: font,
        fontSize: "var(--text-2xs)",
        fontWeight: 700,
        background: done ? "var(--success-text)" : active ? "var(--accent)" : "var(--surface-bg-alt)",
        color: done || active ? "#fff" : "var(--ink-400)",
        // The current stage gets a halo rather than a bigger dot, so every
        // row keeps the same height and the rail stays a straight line.
        boxShadow: active ? "0 0 0 4px var(--accent-bg)" : undefined,
      }}
    >
      {done ? <CheckIcon width={13} height={13} /> : skipped ? "–" : index + 1}
    </div>
  );
}

function ScheduleLine({ schedule }: { schedule: ScheduleInfo }) {
  const online = schedule.mode === "online";
  const where = online ? schedule.meeting_link || "Online" : schedule.location;
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "6px 14px",
        alignItems: "center",
        marginTop: 10,
        padding: "10px 12px",
        borderRadius: "var(--radius)",
        background: "var(--surface-bg)",
        border: "1px solid var(--surface-border)",
        fontFamily: font,
        fontSize: "var(--text-sm)",
        color: "var(--ink-900)",
      }}
    >
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <CalendarIcon width={14} height={14} /> {schedule.date}
      </span>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <ClockIcon width={14} height={14} /> {schedule.time}
      </span>
      {where && (
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            color: "var(--ink-600)",
            minWidth: 0,
            overflowWrap: "anywhere",
          }}
        >
          {online ? <VideoIcon width={14} height={14} /> : <MapPinIcon width={14} height={14} />}
          {where}
        </span>
      )}
    </div>
  );
}

export function StageRow({
  stage,
  index,
  isLast,
  startedIso,
  examScore,
  action,
  closed,
  showSchedule,
}: {
  stage: StageInstance;
  index: number;
  isLast: boolean;
  startedIso: string | null;
  examScore: number | null;
  action: React.ReactNode;
  closed: boolean;
  showSchedule: boolean;
}) {
  const done = stage.status === "complete";
  const active = stage.status === "in_progress" && !closed;
  const schedule = scheduleOf(stage);
  const elapsed = active && startedIso ? elapsedSince(startedIso) : null;

  return (
    <div style={{ display: "flex", gap: 14, alignItems: "stretch" }}>
      {/* Rail: the node, and the connector down to the next stage. */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
        <Node stage={stage} index={index} closed={closed} />
        {!isLast && (
          <div
            style={{
              flex: 1,
              width: 2,
              minHeight: 14,
              background: done ? "var(--success-text)" : "var(--surface-border)",
              opacity: done ? 0.35 : 1,
            }}
          />
        )}
      </div>

      <div style={{ flex: 1, minWidth: 0, paddingBottom: isLast ? 0 : 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline" }}>
          <div
            style={{
              fontFamily: font,
              fontSize: "var(--text-base)",
              fontWeight: active ? 700 : 600,
              // A future stage is legible, not invisible — knowing what is
              // coming is most of the value of showing it at all.
              color: done || active ? "var(--ink-900)" : "var(--ink-600)",
              minWidth: 0,
            }}
          >
            {stage.label}
          </div>
          <div style={{ fontFamily: font, fontSize: "var(--text-xs)", color: "var(--ink-400)", whiteSpace: "nowrap" }}>
            {done && stage.completed_at
              ? shortDate(stage.completed_at)
              : active
              ? elapsed
                ? `In progress · ${elapsed}`
                : "In progress"
              : stage.status === "skipped"
              ? "Skipped"
              : closed && stage.status === "in_progress"
              ? "Not completed"
              : ""}
          </div>
        </div>

        {examScore != null && (
          <div style={{ marginTop: 6 }}>
            {/* Neutral, not success -- a raw score isn't good or bad
                without a passing threshold this app doesn't have, and
                painting every score green (a 20 included) said
                "congratulations" when it hadn't earned one. */}
            <Tag>Scored {examScore} / 100</Tag>
          </div>
        )}

        {/* Only the stage they are actually on expands. */}
        {active && (
          <>
            {schedule && showSchedule && <ScheduleLine schedule={schedule} />}
            {action && <div style={{ marginTop: 12 }}>{action}</div>}
          </>
        )}
      </div>
    </div>
  );
}
