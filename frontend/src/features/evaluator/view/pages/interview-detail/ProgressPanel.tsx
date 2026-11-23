import { Alert } from "../../../../../shared/ui/Alert";
import { Button } from "../../../../../shared/ui/Button";
import { CheckIcon, LockIcon } from "../../../../../shared/ui/icons";
import {
  RECOMMENDATION_OPTIONS,
  SCORECARD_CATEGORIES,
  SCORECARD_ITEM_CODES,
} from "../../../../../shared/lib/scorecard";
import type { EvaluatorRecommendation } from "../../../../../shared/lib/scorecard";
import type { ItemRatingsState } from "./interviewFormat";

/** What is left before the form can go, and the button that sends it —
 * in the rail, so it is in reach from any row rather than only at the
 * foot of the form. Each line of the checklist takes you to its part. */
export function ProgressPanel({
  itemRatings,
  ratedCount,
  recommendation,
  remarksWritten,
  ready,
  submitting,
  submitError,
  draftSavedAt,
  onRatings,
  onRecommendation,
  onRemarks,
}: {
  itemRatings: ItemRatingsState;
  ratedCount: number;
  recommendation: EvaluatorRecommendation | null;
  remarksWritten: boolean;
  ready: boolean;
  submitting: boolean;
  submitError: string | null;
  draftSavedAt: string | null;
  onRatings: () => void;
  onRecommendation: () => void;
  onRemarks: () => void;
}) {
  const total = SCORECARD_ITEM_CODES.length;
  const steps = [
    {
      key: "ratings",
      label: "Rate every item",
      detail: `${ratedCount} of ${total}`,
      done: ratedCount === total,
      onClick: onRatings,
    },
    {
      key: "recommendation",
      label: "Choose a recommendation",
      detail: recommendation ? RECOMMENDATION_OPTIONS.find((o) => o.value === recommendation)?.label : null,
      done: recommendation !== null,
      onClick: onRecommendation,
    },
    {
      key: "remarks",
      label: "Write your remarks",
      detail: null,
      done: remarksWritten,
      onClick: onRemarks,
    },
  ];
  const left = steps.filter((s) => !s.done).length;

  return (
    <section className="ark-panel" aria-labelledby="eval-progress-title">
      <div className="ark-panel__head">
        <h2 id="eval-progress-title" className="ark-panel__title">Your evaluation</h2>
        <span className="ark-panel__count">{ready ? "Ready to submit" : `${left} of 3 left`}</span>
      </div>
      <div className="ark-panel__body ark-eval-progress">
        {/* One mark per item, grouped by area, so the bar also says
            *where* the gaps are. */}
        <div className="ark-eval-meter" role="img" aria-label={`${ratedCount} of ${total} items rated`}>
          {SCORECARD_CATEGORIES.map((category) => (
            <span key={category.code} className="ark-eval-meter__area" style={{ flexGrow: category.items.length }}>
              <span className="ark-eval-meter__marks">
                {category.items.map((item) => {
                  const v = itemRatings[item.code];
                  return <span key={item.code} data-state={v === undefined ? undefined : "rated"} />;
                })}
              </span>
              <span className="ark-eval-meter__code">{category.code}</span>
            </span>
          ))}
        </div>

        <ul className="ark-eval-checks">
          {steps.map((step) => (
            <li key={step.key}>
              <button type="button" className="ark-eval-check" data-done={step.done || undefined} onClick={step.onClick}>
                <span className="ark-eval-check__mark" aria-hidden="true">
                  {step.done && <CheckIcon width={11} height={11} />}
                </span>
                <span className="ark-eval-check__label">{step.label}</span>
                {step.detail && <span className="ark-eval-check__detail">{step.detail}</span>}
              </button>
            </li>
          ))}
        </ul>

        {submitError && (
          <Alert tone="danger" title="The evaluation wasn't submitted">
            {submitError}
          </Alert>
        )}

        <Button
          type="submit"
          form="evaluation-form"
          variant="primary"
          size="lg"
          disabled={submitting || !ready}
          className="ark-eval-progress__submit"
        >
          {submitting ? "Submitting..." : "Submit evaluation"}
        </Button>

        <p className="ark-eval-progress__note">
          <LockIcon width={12} height={12} aria-hidden="true" />
          <span>
            {draftSavedAt
              ? `Draft saved on this device at ${draftSavedAt}. Submitting locks the evaluation.`
              : "Your progress is kept on this device until you submit. Submitting locks it."}
          </span>
        </p>
      </div>
    </section>
  );
}
