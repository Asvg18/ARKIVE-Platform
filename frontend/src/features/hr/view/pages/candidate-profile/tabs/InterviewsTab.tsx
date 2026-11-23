/**
 * The Candidate Profile's Interviews tab: each round, who conducts it,
 * when it is scheduled, the scorecard submitted, and any request from the
 * applicant to move it.
 */

import { useState } from "react";
import type { EvaluatorAssignment, RescheduleResolver, ScheduleEditor, SlotSender } from "../types";
import { Pending } from "../atoms";
import type { CandidateProfile } from "../../../../../../shared/api/pipeline";
import { RoundCard } from "./interviews/RoundCard";

interface InterviewsTabProps {
  profile: CandidateProfile;
  interviewRatings: string[];
  scheduleEditor: ScheduleEditor;
  assignment: EvaluatorAssignment;
  reschedule: RescheduleResolver;
  slotSender: SlotSender;
}

/** State stays on the page (see ../types.ts), except whether each round's
 * feedback is open: that is view state, not a draft, so losing it on a
 * tab switch costs nothing. */
export function InterviewsTab({ profile, interviewRatings, scheduleEditor, assignment, reschedule, slotSender }: InterviewsTabProps) {
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const evaluated = interviewRatings.filter((s) => profile.interview_ratings[s].computed_score != null);
  const allOpen = evaluated.length > 0 && evaluated.every((s) => open.has(s));

  function toggle(stageType: string) {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(stageType)) next.delete(stageType);
      else next.add(stageType);
      return next;
    });
  }

  if (interviewRatings.length === 0) return <Pending />;

  return (
    <div className="ark-interviews">
      <div className="ark-interviews__bar">
        <span>
          <strong>{evaluated.length}</strong> of {interviewRatings.length}{" "}
          {interviewRatings.length === 1 ? "round" : "rounds"} evaluated
        </span>
        {evaluated.length > 1 && (
          <button type="button" className="ark-go" onClick={() => setOpen(allOpen ? new Set() : new Set(evaluated))}>
            {allOpen ? "Collapse all feedback" : "Expand all feedback"}
          </button>
        )}
      </div>

      {interviewRatings.map((stageType) => (
        <RoundCard
          key={stageType}
          stageType={stageType}
          entry={profile.interview_ratings[stageType]}
          requisitionId={profile.requisition_id}
          open={open.has(stageType)}
          onToggle={() => toggle(stageType)}
          scheduleEditor={scheduleEditor}
          assignment={assignment}
          reschedule={reschedule}
          slotSender={slotSender}
        />
      ))}
    </div>
  );
}
