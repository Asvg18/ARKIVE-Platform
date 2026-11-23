import type { StageInstance } from "../../../../../shared/api/applicant";
import { StageRow } from "./StageRow";
import { GUTTER } from "./journeyModel";

/**
 * The dashboard's version of the journey: what's happening now, what's
 * coming, and a door back to everything already done.
 *
 * The ordering is the point. Checking the dashboard is asking one
 * question -- *what, if anything, do I need to do?* -- so the live
 * stage answers first, at full size, with its appointment and button.
 * What's next is reassurance, so it's one quiet line. What's finished
 * is reference, behind a disclosure that stays shut until asked.
 *
 * A closed application skips straight to the summary -- there's no
 * "now" and no "next", and ten greyed-out stages under "You withdrew
 * this application" would just say the page doesn't know it's over.
 */
export function CompactJourney({
  stages,
  currentIndex,
  completed,
  closed,
  action,
  startedIso,
  examScore,
}: {
  stages: StageInstance[];
  currentIndex: number;
  completed: number;
  closed: boolean;
  action: React.ReactNode;
  startedIso: string | null;
  examScore: number | null;
}) {
  const current = currentIndex >= 0 ? stages[currentIndex] : null;
  // Two, not the rest. Three names is a list to read; two is a sentence.
  const upcoming = current ? stages.slice(currentIndex + 1, currentIndex + 3) : [];
  const remaining = current ? stages.length - currentIndex - 1 - upcoming.length : 0;
  const history = closed ? stages.filter((s) => s.status !== "pending") : stages.slice(0, Math.max(currentIndex, 0));

  return (
    <div style={{ marginTop: 16 }}>
      {current && (
        <StageRow
          stage={current}
          index={currentIndex}
          isLast
          startedIso={startedIso}
          examScore={examScore}
          action={action}
          closed={closed}
          showSchedule
        />
      )}

      {upcoming.length > 0 && (
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: 8,
            flexWrap: "wrap",
            marginTop: 4,
            paddingLeft: GUTTER,
          }}
        >
          <span className="ark-meta">Up next</span>
          <span style={{ fontSize: "var(--text-sm)", color: "var(--ink-600)" }}>
            {upcoming.map((s) => s.label).join(", then ")}
            {remaining > 0 && (
              <span style={{ color: "var(--ink-400)" }}>
                {" "}
                &middot; {remaining} more {remaining === 1 ? "step" : "steps"}
              </span>
            )}
          </span>
        </div>
      )}

      {history.length > 0 && (
        /* <details> rather than React state: it is the platform's own
           disclosure, it is keyboard- and screen-reader-correct for
           free, and each card keeps its own open/closed without the
           dashboard having to track one flag per application. */
        <details style={{ marginTop: upcoming.length > 0 ? 12 : 8, paddingLeft: current ? GUTTER : 0 }}>
          <summary
            style={{
              cursor: "pointer",
              listStyle: "none",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: "var(--text-sm)",
              fontWeight: 600,
              color: "var(--ink-600)",
              padding: "4px 0",
            }}
          >
            <span className="ark-disclosure" aria-hidden="true" />
            {closed
              ? `View all ${stages.length} steps`
              : `${completed} completed ${completed === 1 ? "step" : "steps"}`}
          </summary>
          <div style={{ marginTop: 10 }}>
            {history.map((stage, i) => (
              <StageRow
                key={`${stage.stage_type}-${i}`}
                stage={stage}
                index={stages.indexOf(stage)}
                isLast={i === history.length - 1}
                startedIso={null}
                examScore={null}
                action={null}
                closed={closed}
                showSchedule={false}
              />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
