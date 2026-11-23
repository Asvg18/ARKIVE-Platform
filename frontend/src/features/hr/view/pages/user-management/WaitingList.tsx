import { Link } from "react-router-dom";
import type { WaitingInterview } from "../../../../../shared/api/invites";
import { Alert } from "../../../../../shared/ui/Alert";

/** The interviews an evaluator still owes, shown before switching them
 *  off. It doesn't stop the switch-off — people leave whether or not
 *  their queue is empty — it says which rounds need somebody else. */
export function WaitingList({ name, waiting, failed }: { name: string; waiting: WaitingInterview[] | null; failed: boolean }) {
  const first = name.split(" ")[0];
  if (waiting === null) return <p className="ark-field__hint">Checking {first}'s interviews…</p>;
  if (failed) return <p className="ark-field__hint">Couldn't check for interviews still waiting on {first}.</p>;
  if (waiting.length === 0) return <p className="ark-field__hint">No interviews are waiting on {first}.</p>;
  return (
    <Alert
      tone="warning"
      title={`${waiting.length === 1 ? "1 interview is" : `${waiting.length} interviews are`} still waiting on ${first}`}
    >
      <p className="ark-field__hint">
        After deactivating, give each one to someone else from the candidate's Interviews tab.
      </p>
      <ul className="ark-waiting__list">
        {waiting.map((w) => (
          <li key={`${w.application_id}-${w.stage_label}`}>
            <Link to={`/hr/applications/${w.application_id}?tab=interviews`} className="ark-go">
              {w.candidate_name}
            </Link>
            <span>
              {w.stage_label} · {w.job_title}
            </span>
          </li>
        ))}
      </ul>
    </Alert>
  );
}
