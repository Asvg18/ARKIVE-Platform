/** One stage as it is being edited. Only an interview round has a length
 *  (`minutes`): it is saved with the job and cuts the evaluator's free
 *  time into slots. Other stages have no duration or "Visible to
 *  applicant" setting: nothing would save or show them. */
export interface WorkflowStageDraft {
  id: string;
  stageType: string;
  /** Interview rounds only; unset means the round's default length. */
  minutes?: number;
}

let nextId = 0;
export function makeStage(stageType: string): WorkflowStageDraft {
  nextId += 1;
  return { id: `draft-${nextId}`, stageType };
}
