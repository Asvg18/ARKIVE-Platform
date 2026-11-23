import type { AspectRead, CandidateSynthesis, SynthesisRoundRead } from "../../../../../shared/api/pipeline";
import { Avatar } from "../../../../../shared/ui/Avatar";
import { Tag } from "../../../../../shared/ui/Tag";
import { recommendationTone, tierTone } from "../../../../../shared/lib/statusTags";
import { ProgressBar } from "../../../../../shared/ui/ProgressBar";
import { Panel } from "./panels";
import { RECOMMENDATION_LABELS, aspectColor, prose } from "./synthesisStyle";

/** The rubric rolled up by category. The eleven item ratings per round
 * have always been recorded; this is the first screen to add them up. */
export function SynthesisAspects({ aspects }: { aspects: AspectRead[] }) {
  if (aspects.length === 0) return null;

  const ranked = [...aspects].sort((a, b) => b.mean - a.mean);
  const strongest = ranked[0];
  const weakest = ranked[ranked.length - 1];
  const spread = strongest.mean !== weakest.mean;

  return (
    <Panel
      title="Performance by area"
      sub={
        spread ? (
          <>
            Strongest in <b style={{ color: "var(--ink-900)" }}>{strongest.label}</b>, weakest in{" "}
            <b style={{ color: "var(--ink-900)" }}>{weakest.label}</b> · 1–5 scale
          </>
        ) : (
          "Rated evenly across every area · 1–5 scale"
        )
      }
    >
      <div className="ark-aspects">
        {aspects.map((aspect) => (
          <div key={aspect.code}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, marginBottom: 7 }}>
              <span style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--ink-900)", minWidth: 0 }}>{aspect.label}</span>
              <span style={{ display: "flex", alignItems: "baseline", gap: 10, flexShrink: 0 }}>
                <span style={{ fontSize: "var(--text-xs)", color: "var(--ink-600)" }}>{aspect.band}</span>
                <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--ink-950)", fontVariantNumeric: "tabular-nums" }}>
                  {aspect.mean.toFixed(1)}
                </span>
              </span>
            </div>
            <ProgressBar value={aspect.mean} max={5} color={aspectColor(aspect.mean)} />
          </div>
        ))}
      </div>
    </Panel>
  );
}

/** Did the interview chain agree? The chain's own summary first, then
 * one card per round — round, evaluator, score, and their call each in
 * a fixed place, so three rounds compare across at a glance instead of
 * reading as one run of text. */
export function SynthesisAgreement({ agreement }: { agreement: CandidateSynthesis["agreement"] }) {
  if (agreement.rounds.length === 0) return null;

  return (
    <Panel
      title="What the interviewers concluded"
      aside={
        <span className="ark-panel__count">
          {agreement.submitted_rounds} of {agreement.total_rounds} evaluated
        </span>
      }
    >
      {agreement.summary && <p style={{ ...prose, color: "var(--ink-700)" }}>{agreement.summary}</p>}
      <div className="ark-rounds">
        {agreement.rounds.map((round) => (
          <RoundCard key={round.stage_type} round={round} />
        ))}
      </div>
    </Panel>
  );
}

function RoundCard({ round }: { round: SynthesisRoundRead }) {
  const evaluated = round.score != null;
  return (
    <article className="ark-round" data-state={evaluated ? "done" : "pending"}>
      <span className="ark-round__label">{round.label}</span>
      <div className="ark-round__who">
        {round.evaluator_name ? (
          <>
            <Avatar name={round.evaluator_name} size={24} src={round.evaluator_avatar_url} />
            <span className="ark-truncate">{round.evaluator_name}</span>
          </>
        ) : (
          "No evaluator assigned yet"
        )}
      </div>

      {evaluated ? (
        <>
          <div className="ark-round__score">
            <strong>{round.score!.toFixed(1)}</strong>
            <span>/ 5</span>
          </div>
          <div className="ark-round__meter" aria-hidden="true">
            <span style={{ width: `${(round.score! / 5) * 100}%`, background: aspectColor(round.score!) }} />
          </div>
          {(round.tier_label || round.recommendation) && (
            <div className="ark-round__tags">
              {round.tier_label && <Tag tone={tierTone(round.tier)}>{round.tier_label}</Tag>}
              {round.recommendation && (
                <Tag tone={recommendationTone(round.recommendation)}>
                  {RECOMMENDATION_LABELS[round.recommendation] ?? round.recommendation}
                </Tag>
              )}
            </div>
          )}
        </>
      ) : (
        <span style={{ fontSize: "var(--text-sm)", color: "var(--ink-400)" }}>Awaiting the scorecard</span>
      )}
    </article>
  );
}
