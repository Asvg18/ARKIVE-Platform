/** The wizard's frame: the stepper, each step's panel and a labelled
 *  field. */

import { useId, type CSSProperties, type ReactNode } from "react";
import { CheckIcon } from "../../../../../shared/ui/icons";
import { STEPS } from "./builderModel";

/** The steps on one line, joined by a track that fills as each is done.
 *  A finished step is a button back to itself; the ones ahead are not,
 *  because they depend on what the current step produces. A `skipped`
 *  step (Pre-Screening, for a workflow without it) says "Not needed" and
 *  is never a target. */
export function Stepper({
  current,
  onJump,
  skipped,
}: {
  current: number;
  onJump: (step: number) => void;
  skipped: number[];
}) {
  return (
    <ol className="ark-steps" aria-label="Progress" style={{ "--steps": STEPS.length } as CSSProperties}>
      {STEPS.map((s, i) => {
        const isSkipped = skipped.includes(i);
        const state = i < current ? "done" : i === current ? "current" : "todo";
        const inner = (
          <>
            <span className="ark-step__dot">{state === "done" && !isSkipped ? <CheckIcon width={14} height={14} /> : i + 1}</span>
            <span className="ark-step__label">{s.label}</span>
            <span className="ark-step__hint">{isSkipped ? "Not needed" : s.hint}</span>
          </>
        );
        return (
          <li
            key={s.label}
            className="ark-step"
            data-state={state}
            data-skipped={isSkipped || undefined}
            aria-current={state === "current" ? "step" : undefined}
          >
            {state === "done" && !isSkipped ? (
              <button type="button" className="ark-step__btn" onClick={() => onJump(i)}>
                {inner}
              </button>
            ) : (
              <div className="ark-step__btn">{inner}</div>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** One step's panel: heading, the fields, and a footer with the way back
 *  on the left and the way forward on the right. */
export function StepFrame({
  title,
  sub,
  aside,
  back,
  note,
  actions,
  children,
}: {
  title: string;
  sub?: ReactNode;
  aside?: ReactNode;
  back?: ReactNode;
  /** Why the forward action is unavailable, beside it. */
  note?: ReactNode;
  actions: ReactNode;
  children: ReactNode;
}) {
  return (
    <>
      <div className="ark-wizard__head">
        <div className="ark-wizard__heading">
          <h2 className="ark-wizard__title">{title}</h2>
          {sub && <p className="ark-wizard__sub">{sub}</p>}
        </div>
        {aside}
      </div>
      <div className="ark-wizard__body">{children}</div>
      <div className="ark-wizard__foot">
        {back}
        <div className="ark-wizard__foot-end">
          {note && <span className="ark-wizard__note">{note}</span>}
          {actions}
        </div>
      </div>
    </>
  );
}

export function Field({
  label,
  required,
  flag,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  flag?: ReactNode;
  hint?: ReactNode;
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  return (
    <div className="ark-field">
      <div className="ark-field__label-row">
        <label className="ark-field__label" htmlFor={id}>
          {label}
          {required && <span className="ark-field__req">Required</span>}
        </label>
        {flag && <span className="ark-field__flag">{flag}</span>}
      </div>
      {children(id)}
      {hint && <p className="ark-field__hint">{hint}</p>}
    </div>
  );
}
