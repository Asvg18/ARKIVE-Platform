import type { EvaluationRecord } from "../../../../../shared/api/evaluator";
import { ScorecardAreas } from "../../../../../shared/components/ScorecardReadOnly";
import { InfoTip } from "../../../../../shared/ui/InfoTip";
import { LockIcon, SparklesIcon } from "../../../../../shared/ui/icons";
import { RECOMMENDATION_OPTIONS, TIER_COPY } from "../../../../../shared/lib/scorecard";
import { shownText } from "../../../../../shared/lib/displayText";
import { Tag } from "../../../../../shared/ui/Tag";
import { recommendationTone, tierTone } from "../../../../../shared/lib/statusTags";

/** A submitted evaluation's outcome, where the checklist was: what the
 * ratings averaged to, the band that puts them in, and the evaluator's
 * own call — side by side, because they are allowed to disagree. */
export function ResultPanel({ evaluation }: { evaluation: EvaluationRecord }) {
  const tier = TIER_COPY[evaluation.tier];
  return (
    <section className="ark-panel" aria-labelledby="eval-result-title">
      <div className="ark-panel__head">
        <h2 id="eval-result-title" className="ark-panel__title">Your evaluation</h2>
        <span className="ark-panel__count ark-eval-locked">
          <LockIcon width={12} height={12} aria-hidden="true" />
          Locked
        </span>
      </div>
      <div className="ark-panel__body ark-eval-result">
        <div className="ark-eval-result__score">
          <strong>{evaluation.computed_score.toFixed(1)}</strong>
          <span>/ 5 average</span>
        </div>
        <dl className="ark-eval-result__facts">
          <dt>Band</dt>
          <dd>
            <Tag tone={tierTone(evaluation.tier)}>{tier.label}</Tag>
            <InfoTip ariaLabel={`What ${tier.label} means`} width={320}>
              {tier.description}
            </InfoTip>
          </dd>
          <dt>Your call</dt>
          <dd>
            {evaluation.recommendation ? (
              <Tag tone={recommendationTone(evaluation.recommendation)}>
                {RECOMMENDATION_OPTIONS.find((o) => o.value === evaluation.recommendation)?.label ?? evaluation.recommendation}
              </Tag>
            ) : (
              <span className="ark-eval-result__none">Not recorded</span>
            )}
          </dd>
          <dt>Submitted</dt>
          <dd>{new Date(evaluation.submitted_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}</dd>
        </dl>
      </div>
    </section>
  );
}

/** The locked record in the main column: the evaluator's words first,
 * then the AI's summary of the round, then the ratings item by item. */
export function SubmittedRecord({ evaluation }: { evaluation: EvaluationRecord }) {
  return (
    <>
      <section className="ark-panel" aria-labelledby="eval-remarks-title">
        <div className="ark-panel__head">
          <h2 id="eval-remarks-title" className="ark-panel__title">Your remarks</h2>
        </div>
        <div className="ark-panel__body">
          <p className="ark-eval-prose">{evaluation.remarks}</p>
        </div>
      </section>

      {evaluation.ai_summary && (
        <section className="ark-panel" aria-labelledby="eval-summary-title">
          <div className="ark-panel__head">
            <h2 id="eval-summary-title" className="ark-panel__title ark-eval-ai-title">
              <SparklesIcon width={15} height={15} aria-hidden="true" />
              Interview summary
            </h2>
          </div>
          <div className="ark-panel__body">
            <p className="ark-eval-prose">{shownText(evaluation.ai_summary)}</p>
          </div>
        </section>
      )}

      <section className="ark-panel" aria-labelledby="eval-ratings-title">
        <div className="ark-panel__head">
          <div>
            <h2 id="eval-ratings-title" className="ark-panel__title">Ratings</h2>
            <p className="ark-panel__sub">Applicant Preliminary Interview Evaluation Form · HRD-F-APIEF</p>
          </div>
        </div>
        <div className="ark-panel__body">
          <ScorecardAreas itemRatings={evaluation.item_ratings} />
        </div>
      </section>
    </>
  );
}
