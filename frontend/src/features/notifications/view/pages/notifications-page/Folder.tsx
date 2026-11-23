/** One folder in the inbox's folder list, with its unread count. */

import { countLabel } from "../../../model/notifications";
import { BellIcon } from "../../../../../shared/ui/icons";

export function Folder({
  icon: Icon,
  label,
  count,
  active,
  quiet = false,
  onClick,
}: {
  icon: typeof BellIcon;
  label: string;
  count: number;
  active: boolean;
  /** A total, not unread: shown muted. */
  quiet?: boolean;
  onClick: () => void;
}) {
  const shown = countLabel(count);
  return (
    <button type="button" className="ark-inbox__folder" aria-current={active || undefined} onClick={onClick}>
      <Icon width={16} height={16} aria-hidden="true" />
      <span className="ark-inbox__folder-name">{label}</span>
      {shown && (
        <span className="ark-inbox__count" data-quiet={quiet || undefined}>
          {shown}
          <span className="ark-visually-hidden">{quiet ? " notifications" : " unread"}</span>
        </span>
      )}
    </button>
  );
}
