import type { JobListItem } from "../../../../../shared/api/public";
import { initials } from "../../../../../shared/lib/identity";
import { IdentityMark } from "../../../../../shared/ui/IdentityMark";
import { ClockIcon } from "../../../../../shared/ui/icons";
import { Tag } from "../../../../../shared/ui/Tag";
import { deadlineLabel, isSoon, timeAgo } from "./jobListModel";

/** One opening in the list. The selected one takes the accent — the
 *  design system's "this is the one you chose". */
export function Listing({
  job,
  color,
  applied,
  selected,
  onSelect,
}: {
  job: JobListItem;
  color: string;
  applied: boolean;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className="ark-listing"
      aria-current={selected || undefined}
      onClick={onSelect}
    >
      <IdentityMark initials={initials(job.department)} color={color} size="lg" />
      <span className="ark-listing__body">
        <span className="ark-listing__head">
          <span className="ark-listing__title">{job.title}</span>
          {applied && (
            <Tag tone="green" dot>
              Applied
            </Tag>
          )}
        </span>
        <span className="ark-listing__dept">
          {job.department} · {timeAgo(job.created_at)}
        </span>
        {job.description && <span className="ark-listing__desc">{job.description}</span>}
        <span className="ark-listing__foot">
          <span className="ark-listing__deadline" data-soon={isSoon(job.application_deadline) || undefined}>
            <ClockIcon width={12} height={12} aria-hidden="true" />
            {deadlineLabel(job.application_deadline)}
          </span>
          <span>{job.stage_count}-stage process</span>
        </span>
      </span>
    </button>
  );
}
