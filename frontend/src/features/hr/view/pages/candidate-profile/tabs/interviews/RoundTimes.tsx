import { Button } from "../../../../../../../shared/ui/Button";
import type { SlotSender } from "../../types";
import { scheduleInputStyle } from "../../display";
import type { InterviewRatingEntry } from "../../../../../../../shared/api/pipeline";
import { formatDay, formatWindow } from "../../../../../../../shared/lib/scheduleTime";

/** The evaluator → HR → applicant times for one round: what the
 *  evaluator has given, what was sent, and
 *  the editor to tick the slots and send them. */
export function TimesRow({ stageType, entry, slotSender }: { stageType: string; entry: InterviewRatingEntry; slotSender: SlotSender }) {
  const firstName = entry.assigned_evaluator_name?.split(" ")[0] ?? "the evaluator";
  const free = entry.slot_choices.filter((c) => !c.taken);
  const offer = entry.slot_offer;
  const editing = slotSender.editingStage === stageType;

  let status: string;
  if (!entry.assigned_evaluator_id) status = "Assign an evaluator first.";
  else if (offer?.response === "none_work")
    status = `None of the sent times work for the applicant${offer.note ? `: "${offer.note}"` : ""}. Send others.`;
  else if (offer && offer.response === null && !entry.schedule)
    status = `Sent ${offer.slots.length} ${offer.slots.length === 1 ? "time" : "times"}, waiting for the applicant to pick.`;
  else if (offer?.response === "picked" && entry.schedule) status = "The applicant picked a time (shown under Schedule).";
  else if (entry.availability.length === 0) status = `Waiting for ${firstName} to add free times.`;
  else if (free.length === 0) status = `None of ${firstName}'s times are free any more. Ask for more.`;
  else status = `${free.length} free ${entry.duration_minutes}-minute ${free.length === 1 ? "slot" : "slots"} from ${firstName}, not sent yet.`;

  return (
    <>
      <div className="ark-interview__admin-row">
        <span>
          <span className="ark-interview__admin-label">Times</span>
          {status}
        </span>
        {!editing && entry.slot_choices.length > 0 && (
          <Button variant="secondary" onClick={() => slotSender.open(stageType)} style={{ padding: "6px 12px", fontSize: "var(--text-sm)" }}>
            {offer ? "Send New Times" : "Send Times"}
          </Button>
        )}
      </div>
      {editing && <SlotSendEditor entry={entry} slotSender={slotSender} />}
    </>
  );
}

function SlotSendEditor({ entry, slotSender }: { entry: InterviewRatingEntry; slotSender: SlotSender }) {
  const days = [...new Set(entry.slot_choices.map((c) => c.date))];
  const count = slotSender.ticked.length;
  return (
    <div className="ark-interview__editor">
      <p className="ark-field__hint" style={{ margin: "0 0 10px" }}>
        Untick any time you don't want to offer. The applicant picks one; a time another candidate of this evaluator
        takes first drops out for everyone.
        {entry.schedule && " Sending new times replaces the booked time, and the applicant picks again."}
      </p>
      {days.map((day) => (
        <div key={day} style={{ marginBottom: 10 }}>
          <div className="ark-slots__day">{formatDay(day)}</div>
          <div className="ark-slots">
            {entry.slot_choices
              .filter((c) => c.date === day)
              .map((choice) => {
                const key = `${choice.date}|${choice.time}`;
                return (
                  <label key={key} className="ark-slot" data-taken={choice.taken || undefined}>
                    <input
                      type="checkbox"
                      disabled={choice.taken}
                      checked={!choice.taken && slotSender.ticked.includes(key)}
                      onChange={() => slotSender.toggle(key)}
                    />
                    {formatWindow(choice.time, choice.end_time)}
                    {choice.taken && <span className="ark-slot__note">Taken</span>}
                  </label>
                );
              })}
          </div>
        </div>
      ))}
      <div style={{ display: "flex", gap: 8, margin: "4px 0 8px" }}>
        <Button
          type="button"
          variant={slotSender.mode === "in_person" ? "primary" : "outline"}
          onClick={() => slotSender.setMode("in_person")}
          style={{ padding: "6px 12px", fontSize: "var(--text-sm)" }}
        >
          In-Person
        </Button>
        <Button
          type="button"
          variant={slotSender.mode === "online" ? "primary" : "outline"}
          onClick={() => slotSender.setMode("online")}
          style={{ padding: "6px 12px", fontSize: "var(--text-sm)" }}
        >
          Online
        </Button>
      </div>
      {slotSender.mode === "in_person" ? (
        <input
          type="text"
          placeholder="e.g. MSEUF Lucena Campus, Room 204"
          value={slotSender.location}
          onChange={(e) => slotSender.setLocation(e.target.value)}
          style={{ ...scheduleInputStyle, width: "100%", boxSizing: "border-box" }}
        />
      ) : (
        <input
          type="url"
          placeholder="e.g. https://meet.google.com/xxx-xxxx-xxx"
          value={slotSender.meetingLink}
          onChange={(e) => slotSender.setMeetingLink(e.target.value)}
          style={{ ...scheduleInputStyle, width: "100%", boxSizing: "border-box" }}
        />
      )}
      {slotSender.error && <p className="ark-interview__error">{slotSender.error}</p>}
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <Button variant="primary" onClick={slotSender.send} disabled={slotSender.sending || count === 0} style={{ padding: "8px 16px" }}>
          {slotSender.sending ? "Sending..." : `Send ${count} ${count === 1 ? "Time" : "Times"} to Applicant`}
        </Button>
        <Button variant="ghost" onClick={slotSender.close} disabled={slotSender.sending} style={{ padding: "8px 16px" }}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
