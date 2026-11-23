/** Helpers shared by JobStatusDialog and the pages that open it. Kept
 *  out of the component file so fast refresh keeps working there. */

import type { RequisitionListItem } from "../../../shared/api/pipeline";

/** The fields a status change needs — present on both the Job Openings
 *  row and the job's own detail page. */
export type StatusJob = Pick<
  RequisitionListItem,
  "id" | "title" | "status" | "application_deadline" | "active_candidate_count"
>;

export function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

/** The one way forward for a job's status: Close for a live posting,
 *  Publish or Repost for one that isn't — never both. */
export function statusActionLabel(status: StatusJob["status"]): { label: string; description: string } {
  if (status === "open") {
    return { label: "Close Job Opening", description: "Stops new applications. You can repost it later." };
  }
  return status === "draft"
    ? { label: "Publish Job Opening", description: "Puts it on the public job board." }
    : { label: "Repost Job Opening", description: "Opens it to new applicants again." };
}
