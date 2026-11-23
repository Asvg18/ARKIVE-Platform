import type { StageInstance } from "../../../../../shared/api/applicant";

/**
 * A segmented bar, one segment per stage — the "where am I" answer at a
 * glance, before any reading. Segments rather than a continuous fill
 * because the stages are discrete and countable, and a smooth 40% would
 * imply a precision the pipeline does not have.
 */
export function ProgressRail({ stages, closed }: { stages: StageInstance[]; closed: boolean }) {
  return (
    <div style={{ display: "flex", gap: 3 }}>
      {stages.map((stage, i) => {
        const done = stage.status === "complete";
        const active = stage.status === "in_progress" && !closed;
        return (
          <div
            key={`${stage.stage_type}-${i}`}
            title={stage.label}
            style={{
              height: 5,
              flex: 1,
              borderRadius: 999,
              background: done
                ? "var(--success-text)"
                : active
                ? "var(--accent)"
                : "var(--surface-bg-alt)",
            }}
          />
        );
      })}
    </div>
  );
}
