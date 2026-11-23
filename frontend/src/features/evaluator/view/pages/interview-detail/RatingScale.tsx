/** The 1-5 rating control and the key to the scale. */

import { useRef, type KeyboardEvent } from "react";
import { RATING_SCALE_LEGEND } from "../../../../../shared/lib/scorecard";
import { RATING_OPTIONS, RATING_WORD } from "./interviewFormat";

/** A 1–5 scale as one radio group: arrow keys move along it, and
 * a number key answers straight away, so the form can be filled
 * from the keyboard a row at a time with Tab.
 *
 * The cells up to the chosen number take a tint and the chosen one the
 * accent, so a column of answers reads as a set of bars — a 2 among 4s
 * shows without reading a single digit. */
export function RatingScale({
  value,
  labelledBy,
  onChange,
}: {
  value: number | undefined;
  labelledBy: string;
  onChange: (value: number) => void;
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const selectedIndex = value === undefined ? -1 : RATING_OPTIONS.findIndex((o) => o.value === value);
  const focusIndex = selectedIndex === -1 ? 0 : selectedIndex;

  function choose(index: number) {
    onChange(RATING_OPTIONS[index].value);
    refs.current[index]?.focus();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const count = RATING_OPTIONS.length;
    const current = refs.current.findIndex((el) => el === document.activeElement);
    const from = current === -1 ? focusIndex : current;
    let next: number | null = null;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = (from + 1) % count;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = (from - 1 + count) % count;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = count - 1;
    else if (/^[1-5]$/.test(e.key)) next = Number(e.key) - 1;
    if (next === null) return;
    e.preventDefault();
    choose(next);
  }

  function optionButton(option: (typeof RATING_OPTIONS)[number], index: number, className: string) {
    const checked = index === selectedIndex;
    const filled = typeof value === "number" && option.value < value;
    const word = RATING_WORD[option.value];
    return (
      <button
        key={option.label}
        ref={(el) => { refs.current[index] = el; }}
        type="button"
        role="radio"
        aria-checked={checked}
        aria-label={`${option.value}, ${word}`}
        title={word}
        tabIndex={index === focusIndex ? 0 : -1}
        className={className}
        data-filled={filled || undefined}
        onClick={() => choose(index)}
      >
        {option.label}
      </button>
    );
  }

  return (
    <div
      role="radiogroup"
      aria-labelledby={labelledBy}
      className="ark-rate"
      onKeyDown={handleKeyDown}
    >
      <span className="ark-rate__scale">
        {RATING_OPTIONS.map((option, i) => optionButton(option, i, "ark-rate__opt"))}
      </span>
    </div>
  );
}

/** The form's own scale, in its words. Used to be a strip at the top of
 * the form, which the eighth row had long since scrolled away from. */
export function ScaleKey({ compact = false }: { compact?: boolean }) {
  return (
    <div className="ark-scale-key" data-compact={compact || undefined}>
      <ul className="ark-scale-key__list">
        {[...RATING_SCALE_LEGEND].reverse().map(([n, word]) => (
          <li key={n}>
            <span className="ark-scale-key__n">{n}</span>
            {word}
          </li>
        ))}
      </ul>
      {!compact && (
        <p className="ark-scale-key__note">
          Every item needs a rating. On a focused row, press 1–5 to answer.
        </p>
      )}
    </div>
  );
}

export function ScalePanel() {
  return (
    <section className="ark-panel ark-eval__scale" aria-labelledby="eval-scale-title">
      <div className="ark-panel__head">
        <h2 id="eval-scale-title" className="ark-panel__title">Rating scale</h2>
      </div>
      <div className="ark-panel__body">
        <ScaleKey />
      </div>
    </section>
  );
}
