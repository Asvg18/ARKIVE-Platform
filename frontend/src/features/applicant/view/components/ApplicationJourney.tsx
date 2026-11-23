/**
 * The applicant's view of where their application stands, as a vertical
 * journey through its stages.
 */

import { Link } from "react-router-dom";
import type { ApplicationDetail, StageInstance } from "../../../../shared/api/applicant";
import { Button } from "../../../../shared/ui/Button";
import { OutcomeBanner } from "./journey/OutcomeBanner";
import { font, startedAt } from "./journey/journeyModel";
import { ProgressRail } from "./journey/ProgressRail";
import { CompactJourney } from "./journey/CompactJourney";
import { StageRow } from "./journey/StageRow";

/** Vertical, not horizontal: these workflows run 6 to 10 stages, a row of
 * ten wraps mid-sequence so its arrows stop meaning "next", and a column
 * has room for what matters on each stage (a date, an appointment, a
 * score). Only the current stage expands, so everything the applicant
 * must act on shows without a click. */
export function ApplicationJourney({
  application,
  stageScreenBelow = false,
  compact = false,
}: {
  application: ApplicationDetail;
  /** Dashboard mode. The full journey lists every stage, right on the
   * detail page -- you opened one application, so its whole shape is
   * what you came for. Wrong on the dashboard: two applications of
   * seven and ten stages put seventeen mostly-empty rows on screen,
   * and the one that matters is buried among them.
   *
   * Compact shows only what an applicant can act on or is waiting for:
   * the current stage in full, the next one or two named in a line,
   * everything already done folded into an expandable summary. Nothing
   * removed, only deferred. */
  compact?: boolean;
  /** True when the current stage's own screen renders underneath this
   * journey -- the stage detail page, not the dashboard. That screen
   * already *is* the action, so the journey drops the button that would
   * link back to the page you're on, and drops the appointment line
   * (the screen below states it in full). One flag, not two, since both
   * follow from the same fact and must never disagree. */
  stageScreenBelow?: boolean;
}) {
  const stages = application.stage_instances;
  const completed = stages.filter((s) => s.status === "complete").length;
  // "flagged" stays open: the applicant is still in the running, HR is
  // simply reviewing them by hand.
  const closed = application.status !== "active" && application.status !== "flagged";
  const currentIndex = closed ? -1 : stages.findIndex((s) => s.status === "in_progress");
  const current = currentIndex >= 0 ? stages[currentIndex] : null;

  // examination_results is keyed by the same stage_type as the instance,
  // so an exam stage can show what they scored the moment HR records it.
  const scoreFor = (stage: StageInstance): number | null =>
    application.examination_results[stage.stage_type]?.score ?? null;

  const action =
    !stageScreenBelow && application.status === "active" && current ? (
      <Link to={`/applicant/applications/${application.id}`} style={{ textDecoration: "none" }}>
        <Button variant="primary">Continue: {current.label}</Button>
      </Link>
    ) : null;

  return (
    <div>
      <OutcomeBanner status={application.status} />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, marginBottom: 8 }}>
        <div style={{ fontFamily: font, fontSize: "var(--text-xs)", fontWeight: 700, color: "var(--ink-600)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
          {current
            ? `Stage ${currentIndex + 1} of ${stages.length}`
            : `${completed} of ${stages.length} stages complete`}
        </div>
        {application.exam_percentile != null && (
          <div style={{ fontFamily: font, fontSize: "var(--text-xs)", color: "var(--ink-600)" }}>
            Exam percentile {application.exam_percentile}
          </div>
        )}
      </div>

      <ProgressRail stages={stages} closed={closed} />

      {compact ? (
        <CompactJourney
          stages={stages}
          currentIndex={currentIndex}
          completed={completed}
          closed={closed}
          action={action}
          startedIso={currentIndex >= 0 ? startedAt(stages, currentIndex) : null}
          examScore={current ? scoreFor(current) : null}
        />
      ) : (
        <div style={{ marginTop: 18 }}>
          {stages.map((stage, i) => (
            <StageRow
              key={`${stage.stage_type}-${i}`}
              stage={stage}
              index={i}
              isLast={i === stages.length - 1}
              startedIso={startedAt(stages, i)}
              examScore={scoreFor(stage)}
              action={action}
              closed={closed}
              showSchedule={!stageScreenBelow}
            />
          ))}
        </div>
      )}
    </div>
  );
}
