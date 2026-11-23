import { applicationStatusTone } from "../../../../../shared/lib/statusTags";
import { CheckIcon, InfoIcon, LogOutIcon } from "../../../../../shared/ui/icons";

/** The outcome in two lines — a title in the status's own word, and a
 *  sentence under it — with an icon carrying the colour. */
const OUTCOME: Record<string, { title: string; text: string; icon: "check" | "info" | "leave" }> = {
  hired: { title: "Accepted", text: "You've been accepted for this position.", icon: "check" },
  rejected: { title: "Unlikely to progress", text: "This application won't be taken further.", icon: "info" },
  withdrawn: { title: "Withdrawn", text: "You withdrew this application.", icon: "leave" },
};

/**
 * States the outcome at the head of the journey.
 *
 * The result is the most important thing on the card, so it is said in
 * words, once, above the stages that led to it; without it a closed
 * application would read as still running. An icon in the status colour
 * beside a title and a line, on the card's own white: colour on the
 * mark, not the whole block, as elsewhere in the portal.
 */
export function OutcomeBanner({ status }: { status: string }) {
  const outcome = OUTCOME[status];
  if (!outcome) return null;
  const Icon = outcome.icon === "check" ? CheckIcon : outcome.icon === "info" ? InfoIcon : LogOutIcon;
  return (
    <div className="ark-outcome-banner" data-tone={applicationStatusTone(status)}>
      <span className="ark-outcome-banner__icon" aria-hidden="true">
        <Icon width={16} height={16} strokeWidth={outcome.icon === "check" ? 3 : 2} />
      </span>
      <span>
        <span className="ark-outcome-banner__title">{outcome.title}</span>
        <span className="ark-outcome-banner__text">{outcome.text}</span>
      </span>
    </div>
  );
}
