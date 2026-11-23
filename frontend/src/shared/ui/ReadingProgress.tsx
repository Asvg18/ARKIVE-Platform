import { useEffect, useId, useState } from "react";
import { CheckIcon } from "./icons";

/**
 * What an applicant watches while ARKIVE reads their resume, or saves
 * their application and matches it to the job:
 * a document card under a gentle scanning light, a percent ring, and a
 * checklist that ticks off what is being read.
 *
 * The server reports nothing until it is done, so the percent is an
 * honest estimate: it climbs quickly at first, slows as it nears 90% and
 * never passes 90% on its own. Each item ticks as the estimate passes it,
 * and `done` (the real response) takes it to 100% with every item ticked.
 * An error is not shown here: the screen swaps back to the form, with the
 * error and the way to fill it in by hand.
 */

export interface ReadingStep {
  label: string;
  /** Ticked once the estimate reaches this percentage. */
  until: number;
}

/** Estimated percentage after `elapsedMs` of a request expected to take
 *  about `expectedMs`: about 57% at the expected time, never above 90%. */
export function estimatedPercent(elapsedMs: number, expectedMs: number): number {
  return Math.min(90, 90 * (1 - Math.exp(-elapsedMs / expectedMs)));
}

/** How many steps are ticked at `percent`. */
export function stepsDone(percent: number, steps: ReadingStep[]): number {
  return steps.filter((step) => percent >= step.until).length;
}

/** What a screen reader hears: once per finished step, not once per
 *  percent, so the announcements stay calm. */
export function announcement(title: string, steps: ReadingStep[], ticked: number, done: boolean): string {
  if (done) return `${title}: done.`;
  if (ticked === 0) return "";
  return `${steps[ticked - 1].label}: done.`;
}

export function ReadingProgress({
  title,
  steps,
  expectedMs,
  done = false,
  fileName,
}: {
  /** "Reading your resume": the heading, and the progress bar's name. */
  title: string;
  steps: ReadingStep[];
  expectedMs: number;
  done?: boolean;
  /** The file being read, shown under the heading. */
  fileName?: string;
}) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (done) return;
    const started = Date.now() - elapsed;
    const timer = window.setInterval(() => setElapsed(Date.now() - started), 200);
    return () => window.clearInterval(timer);
    // `elapsed` only seeds the start time; re-running on every tick would
    // restart the interval five times a second.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [done]);

  const titleId = useId();
  const percent = done ? 100 : Math.round(estimatedPercent(elapsed, expectedMs));
  const ticked = done ? steps.length : stepsDone(percent, steps);

  return (
    <section className="ark-reading" data-done={done || undefined} aria-labelledby={titleId}>
      <div className="ark-reading__visual">
        <div className="ark-reading__doc" aria-hidden="true">
          <span className="ark-reading__line ark-reading__line--head" />
          <span className="ark-reading__line" />
          <span className="ark-reading__line ark-reading__line--short" />
          <span className="ark-reading__gap" />
          <span className="ark-reading__line" />
          <span className="ark-reading__line ark-reading__line--mid" />
          <span className="ark-reading__line" />
          <span className="ark-reading__line ark-reading__line--short" />
          <span className="ark-reading__scan" />
        </div>
        <div
          className="ark-reading__ring"
          role="progressbar"
          aria-label={title}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
        >
          <svg viewBox="0 0 64 64" aria-hidden="true">
            <circle className="ark-reading__track" cx="32" cy="32" r="27" />
            <circle
              className="ark-reading__arc"
              cx="32"
              cy="32"
              r="27"
              pathLength={100}
              style={{ ["--ring-pct" as string]: percent }}
            />
          </svg>
          <span className="ark-reading__pct" aria-hidden="true">
            {percent}%
          </span>
        </div>
      </div>

      <div className="ark-reading__body">
        <h3 id={titleId} className="ark-reading__title">
          {title}
        </h3>
        {fileName && <p className="ark-reading__file">{fileName}</p>}

        <ol className="ark-reading__steps">
          {steps.map((step, index) => {
            const state = index < ticked ? "done" : index === ticked && !done ? "current" : "pending";
            return (
              <li key={step.label} className="ark-reading__step" data-state={state}>
                <span className="ark-reading__mark" aria-hidden="true">
                  {state === "done" && <CheckIcon width={11} height={11} strokeWidth={3} />}
                </span>
                {step.label}
                <span className="ark-visually-hidden">
                  {state === "done" ? ", done" : state === "current" ? ", reading now" : ""}
                </span>
              </li>
            );
          })}
        </ol>

        <p className="ark-reading__note">
          {done ? "Done." : "This usually takes under a minute. Please keep this page open."}
        </p>
      </div>

      <p className="ark-visually-hidden" aria-live="polite">
        {announcement(title, steps, ticked, done)}
      </p>
    </section>
  );
}
