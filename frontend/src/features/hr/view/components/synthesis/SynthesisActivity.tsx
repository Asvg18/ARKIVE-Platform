import type { CandidateSynthesis } from "../../../../../shared/api/pipeline";
import { Tag } from "../../../../../shared/ui/Tag";
import { DisclosurePanel } from "./panels";
import { AGENT_BADGE } from "./synthesisStyle";

/** The audit trail. Kept, because it is the evidence that the agents
 * actually acted on this candidate; collapsed, because it is not
 * something HR needs while deciding. */
export function SynthesisActivity({
  agents,
  agentTrail,
  open,
}: {
  agents: CandidateSynthesis["agents"];
  agentTrail: CandidateSynthesis["agent_trail"];
  open: boolean;
}) {
  const ran = agents.filter((a) => a.status === "ran").length;
  // Only agents that can actually run count towards the total. A
  // `derived` agent (Decision Support is a pure function recomputed on
  // every read) has no run event by design, and a `not_applicable` one
  // has no stage in this workflow — counting either would render as
  // "7 of 8 agents have run", which reads as one having failed.
  const expected = agents.filter((a) => a.status === "ran" || a.status === "pending").length;
  const lastRun = agentTrail[0]?.created_at;

  return (
    <DisclosurePanel
      title="System activity"
      detail={`${ran} of ${expected} agents have run` + (lastRun ? ` · last ${new Date(lastRun).toLocaleDateString()}` : "")}
      open={open}
    >
      <div style={{ padding: "16px 24px 20px" }}>
        <div style={{ display: "grid", gap: 10 }}>
          {agents.map((a) => {
            const badge = AGENT_BADGE[a.status];
            return (
              <div
                key={a.agent_name}
                style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, paddingBottom: 10, borderBottom: "1px solid var(--hairline)" }}
              >
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: a.status === "not_applicable" ? "var(--ink-400)" : "var(--ink-900)" }}>
                    {a.label}
                    {a.run_count > 1 && <span style={{ color: "var(--ink-600)", fontWeight: 500 }}> · {a.run_count} runs</span>}
                  </div>
                  <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-600)", marginTop: 2, lineHeight: 1.5 }}>{a.duty}</div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
                  {a.last_run_at && (
                    <span style={{ fontSize: "var(--text-xs)", color: "var(--ink-600)", whiteSpace: "nowrap" }}>
                      {new Date(a.last_run_at).toLocaleDateString()}
                    </span>
                  )}
                  <Tag tone={badge.tone} dot>
                    {badge.label}
                  </Tag>
                </div>
              </div>
            );
          })}
        </div>

        {agentTrail.length > 0 && (
          <div style={{ marginTop: 18 }}>
            <span className="ark-eyebrow-quiet">Execution log</span>
            <div style={{ display: "grid", gap: 6, marginTop: 8 }}>
              {agentTrail.map((run) => (
                <div key={run.id} style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: "var(--text-xs)", color: "var(--ink-600)" }}>
                  <span style={{ color: "var(--ink-900)" }}>
                    {run.label}
                    <span style={{ color: "var(--ink-600)" }}> · {run.triggered_by_stage_label}</span>
                  </span>
                  <span style={{ whiteSpace: "nowrap" }}>{new Date(run.created_at).toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </DisclosurePanel>
  );
}
