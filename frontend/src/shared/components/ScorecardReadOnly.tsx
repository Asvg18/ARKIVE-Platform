import { RATING_SCALE_LEGEND, SCORECARD_CATEGORIES } from "../lib/scorecard";

const RATING_WORD = Object.fromEntries(RATING_SCALE_LEGEND) as Record<number, string>;

/** Five marks, as many filled as the rating, in the brand colour. A 1
 * or 2 — "Improvement Needed" and below on the form's own scale — turns
 * amber and tints its whole row, so the weak items find the eye without
 * reading every number (the row does the work: amber marks alone sit too
 * close to the brand's red-orange to stand out). */
function RatingPips({ rating }: { rating: number }) {
  return (
    <span className="ark-rubric__pips" data-low={rating <= 2 || undefined} aria-hidden="true">
      {[1, 2, 3, 4, 5].map((n) => (
        <span key={n} data-on={n <= rating || undefined} />
      ))}
    </span>
  );
}

/**
 * The form's four areas, each its own block: a heading band with the
 * area's letter, name and average, then its items with the rating shown
 * as marks, number and the form's word for it.
 *
 * Ratings are not drawn in the attention colour, so the areas stay apart
 * and nothing shouts. Both readers place it beneath the evaluator's
 * conclusion: HR's Candidate Profile (Interviews tab) and the evaluator's
 * own locked view (InterviewDetailPage). The file keeps the name of the
 * ScorecardReadOnly wrapper those views replaced.
 */
export function ScorecardAreas({ itemRatings }: { itemRatings: Record<string, number | null> }) {
  return (
    <div className="ark-rubric">
      {SCORECARD_CATEGORIES.map((category) => {
        const rated = category.items
          .map((item) => itemRatings[item.code])
          .filter((r): r is number => r != null);
        const mean = rated.length > 0 ? rated.reduce((a, b) => a + b, 0) / rated.length : null;
        return (
          <section key={category.code} className="ark-rubric__area" aria-label={category.label}>
            <header className="ark-rubric__head">
              <span className="ark-rubric__code" aria-hidden="true">
                {category.code}
              </span>
              <span className="ark-rubric__title">{category.label}</span>
              {mean != null && (
                <span className="ark-rubric__avg">
                  {mean.toFixed(1)}
                  <small> avg</small>
                </span>
              )}
            </header>
            <ul className="ark-rubric__items">
              {category.items.map((item) => {
                const rating = itemRatings[item.code];
                return (
                  <li key={item.code} data-low={(rating != null && rating <= 2) || undefined}>
                    <span className="ark-rubric__label">{item.label}</span>
                    {rating == null ? (
                      <span className="ark-rubric__na">Not rated</span>
                    ) : (
                      <span className="ark-rubric__rating">
                        <RatingPips rating={rating} />
                        <strong>{rating}</strong>
                        <span className="ark-rubric__word">{RATING_WORD[rating]}</span>
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
