/** The pipeline page's shared rules and shapes: what counts as still in
 *  play, the rail's sections, and one opening as the rail sees it. */
import type { CSSProperties } from "react";
import type { ApplicationListItem, RequisitionListItem, RequisitionStatus } from "../../../../../shared/api/pipeline";

/** Still in play. Matches PipelineBoard's own `isMovable` — the number
 *  HR cares about per opening is who is still moving, not how many rows
 *  the database holds. */
export function isOpen(application: ApplicationListItem): boolean {
  return application.status === "active" || application.status === "flagged";
}

export const ellipsis: CSSProperties = { whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" };

/** The rail's sections, in the order HR reads them: what is hiring now,
 *  what has not gone up yet, what is finished. */
export const RAIL_SECTIONS: { status: RequisitionStatus; label: string }[] = [
  { status: "open", label: "Open" },
  { status: "draft", label: "Drafts" },
  { status: "closed", label: "Closed" },
];

export const JOB_STATUS_LABEL: Record<RequisitionStatus, string> = {
  open: "Open",
  draft: "Draft",
  closed: "Closed",
};

/** One opening as the rail sees it: the posting, its candidates, and how
 *  many of them the current search matched. */
export interface JobEntry {
  job: RequisitionListItem;
  /** Everyone in this pipeline, before the search. */
  all: ApplicationListItem[];
  /** What to render for this opening under the current search. The whole
   *  pipeline when the opening itself is what matched — searching a job
   *  title means "show me this job", not "show me nobody". */
  visible: ApplicationListItem[];
}

/** A rail section with the openings it shows. */
export interface RailSection {
  status: RequisitionStatus;
  label: string;
  entries: JobEntry[];
}

/** One row of the candidate list, ranked by match score (null: unscored). */
export interface RankedRow {
  application: ApplicationListItem;
  rank: number | null;
}
