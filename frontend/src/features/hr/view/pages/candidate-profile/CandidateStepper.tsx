import type { ApplicationListItem } from "../../../../../shared/api/pipeline";
import { ChevronLeftIcon, ChevronRightIcon } from "../../../../../shared/ui/icons";

/** Previous / next candidate in the same pipeline, with the position
 *  ("3 of 12"); K and J are the keyboard shortcuts the page listens for. */
export function CandidateStepper({
  position,
  siblings,
  previous,
  next,
  goTo,
}: {
  position: number;
  siblings: ApplicationListItem[];
  previous: ApplicationListItem | null;
  next: ApplicationListItem | null;
  goTo: (candidate: ApplicationListItem) => void;
}) {
  return (
    <nav className="ark-stepper" aria-label="Candidates in this pipeline">
      <button
        type="button"
        className="ark-stepper__btn"
        onClick={() => previous && goTo(previous)}
        disabled={!previous}
        aria-label={previous ? `Previous candidate: ${previous.applicant_name}` : "Previous candidate"}
        aria-keyshortcuts="K"
        title={previous ? `${previous.applicant_name} (K)` : undefined}
      >
        <ChevronLeftIcon width={15} height={15} />
      </button>
      <span className="ark-stepper__count">
        {position + 1} of {siblings.length}
      </span>
      <button
        type="button"
        className="ark-stepper__btn"
        onClick={() => next && goTo(next)}
        disabled={!next}
        aria-label={next ? `Next candidate: ${next.applicant_name}` : "Next candidate"}
        aria-keyshortcuts="J"
        title={next ? `${next.applicant_name} (J)` : undefined}
      >
        <ChevronRightIcon width={15} height={15} />
      </button>
    </nav>
  );
}
