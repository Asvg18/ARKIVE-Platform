import { useId, useState, type ReactNode, type SVGProps } from "react";
import type { CandidateSynthesis, HeadlineSignal } from "../../../../../shared/api/pipeline";
import { shownText } from "../../../../../shared/lib/displayText";
import { ArrowRightIcon, BriefcaseIcon, ChevronDownIcon, PencilIcon, PeopleIcon } from "../../../../../shared/ui/icons";

const SIGNAL_ICON: Record<HeadlineSignal["key"], (props: SVGProps<SVGSVGElement>) => ReactNode> = {
  evaluators: PeopleIcon,
  exam_rank: PencilIcon,
  requirement_gaps: BriefcaseIcon,
};

/** Where each fact is argued in full — the Candidate Profile maps these
 * to its tabs. */
const SIGNAL_LINK: Record<HeadlineSignal["key"], string> = {
  evaluators: "Open the interviews",
  exam_rank: "Open the examination",
  requirement_gaps: "See the resume read",
};

/** A requirement list can run long; the rest is one click away. */
const SIGNAL_ITEM_LIMIT = 3;

/**
 * The signals: what the evidence says needs a look, folded into one line
 * (a dot per fact, coloured by which way it points) that opens on
 * request. Each fact leads to the tab that argues it in full when
 * `onOpenSignal` is given.
 *
 * There is no overall score (see the note at the top of this file), so
 * with no signals there is nothing to show and it renders nothing.
 */
export function SynthesisVerdict({
  synthesis,
  expanded = false,
  onOpenSignal,
}: {
  synthesis: CandidateSynthesis;
  /** Open the facts from the start — the Pre-201 package's permanent record. */
  expanded?: boolean;
  onOpenSignal?: (key: HeadlineSignal["key"]) => void;
}) {
  const [open, setOpen] = useState(expanded);
  const drawerId = useId();
  const signals = synthesis.headline.signals;
  const toReview = signals.filter((s) => s.tone === "attention").length;

  if (signals.length === 0) return null;

  return (
    <section className="ark-verdict" aria-label="Signals">
      <div className="ark-verdict__head">
        <span className="ark-eyebrow-quiet">Signals</span>
      </div>
      <div className="ark-verdict__signals">
        <button
          type="button"
          className="ark-verdict__toggle"
          aria-expanded={open}
          aria-controls={drawerId}
          onClick={() => setOpen((v) => !v)}
        >
          <span className="ark-verdict__dots" aria-hidden="true">
            {signals.map((s) => (
              <span key={s.key} data-tone={s.tone} />
            ))}
          </span>
          <span className="ark-verdict__summary">
            {signals.length} {signals.length === 1 ? "signal" : "signals"}
            {toReview > 0 && <span className="ark-verdict__flag"> · {toReview} to review</span>}
          </span>
          <span className="ark-verdict__cta">
            {open ? "Hide details" : "View details"}
            <ChevronDownIcon width={14} height={14} aria-hidden="true" />
          </span>
        </button>

        <div className="ark-drawer" id={drawerId} data-open={open || undefined}>
          <div>
            <ul className="ark-signals">
              {signals.map((s) => (
                <SignalRow key={s.key} signal={s} onOpen={onOpenSignal} />
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

function SignalRow({
  signal,
  onOpen,
}: {
  signal: HeadlineSignal;
  onOpen?: (key: HeadlineSignal["key"]) => void;
}) {
  const Icon = SIGNAL_ICON[signal.key];
  const shown = signal.items.slice(0, SIGNAL_ITEM_LIMIT);
  const hidden = signal.items.length - shown.length;

  return (
    <li className="ark-signal" data-tone={signal.tone}>
      <span className="ark-signal__icon" aria-hidden="true">
        <Icon width={15} height={15} />
      </span>
      <div style={{ minWidth: 0 }}>
        <span className="ark-signal__label">{signal.label}</span>
        <p className="ark-signal__detail">{signal.detail}</p>
        {shown.length > 0 && (
          <ul className="ark-signal__items">
            {shown.map((item) => (
              <li key={item}>{shownText(item)}</li>
            ))}
            {hidden > 0 && <li data-more>and {hidden} more</li>}
          </ul>
        )}
        {onOpen && (
          <button type="button" className="ark-go" onClick={() => onOpen(signal.key)}>
            {SIGNAL_LINK[signal.key]}
            <ArrowRightIcon width={13} height={13} aria-hidden="true" />
          </button>
        )}
      </div>
    </li>
  );
}
