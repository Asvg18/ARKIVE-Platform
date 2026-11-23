/**
 * The prop groups the Candidate Profile's tabs are given. The page owns
 * this state because tab bodies are conditionally rendered, so state held
 * in one would be lost when HR clicked another tab, along with a
 * half-typed exam score or a partly filled schedule; and the props come
 * in groups because the groups are real (the schedule editor is one
 * editor used by two tabs, and moves as a unit).
 */

import type { Dispatch, SetStateAction } from "react";

import type { RequisitionEvaluator } from "../../../../../shared/api/pipeline";

/** Scheduling an examination sitting or an interview round. Shared by both
 * of those tabs, which is why it is a group and not two near-copies. */
export interface ScheduleEditor {
  editingStage: string | null;
  setEditingStage: Dispatch<SetStateAction<string | null>>;
  date: string;
  setDate: Dispatch<SetStateAction<string>>;
  time: string;
  setTime: Dispatch<SetStateAction<string>>;
  mode: "in_person" | "online";
  setMode: Dispatch<SetStateAction<"in_person" | "online">>;
  location: string;
  setLocation: Dispatch<SetStateAction<string>>;
  meetingLink: string;
  setMeetingLink: Dispatch<SetStateAction<string>>;
  submitting: boolean;
  error: string | null;
  /** Opens the editor pre-filled from any schedule already recorded. */
  open: (stageType: string) => void;
  submit: () => Promise<void>;
}

/** Recording the score of a sitting that has already happened. */
export interface ExamScoreEditor {
  editingStage: string | null;
  setEditingStage: Dispatch<SetStateAction<string | null>>;
  input: string;
  setInput: Dispatch<SetStateAction<string>>;
  /** The day the exam was sat, YYYY-MM-DD. */
  takenOn: string;
  setTakenOn: Dispatch<SetStateAction<string>>;
  submitting: boolean;
  error: string | null;
  setError: Dispatch<SetStateAction<string | null>>;
  submit: (stageType: string) => Promise<void>;
}

/** Approving or denying the slot the Exam Scheduling Agent proposed. */
export interface ExamBookingResolver {
  resolvingId: number | null;
  error: string | null;
  /** HR may override the agent's pick before approving. */
  slotOverride: Record<number, number>;
  setSlotOverride: Dispatch<SetStateAction<Record<number, number>>>;
  resolve: (bookingId: number, decision: "approve" | "deny", examSlotId?: number) => Promise<void>;
}

/** Marking a candidate shortlisted or not -- a plain outcome recorded
 *  once, with optional notes. */
export interface ShortlistingEditor {
  editingStage: string | null;
  setEditingStage: Dispatch<SetStateAction<string | null>>;
  outcome: "shortlisted" | "not_shortlisted";
  setOutcome: Dispatch<SetStateAction<"shortlisted" | "not_shortlisted">>;
  notes: string;
  setNotes: Dispatch<SetStateAction<string>>;
  submitting: boolean;
  error: string | null;
  setError: Dispatch<SetStateAction<string | null>>;
  submit: (stageType: string) => Promise<void>;
}

/** Putting one of the job's evaluators on one interview round. */
export interface EvaluatorAssignment {
  pool: RequisitionEvaluator[];
  assigningStage: string | null;
  error: { stage: string; message: string } | null;
  assign: (stageType: string, evaluatorId: number | null) => Promise<void>;
}

/** Answering an applicant's request to move an interview. */
export interface RescheduleResolver {
  resolvingId: number | null;
  error: string | null;
  resolve: (
    requestId: number,
    decision: "approve" | "deny",
    date?: string,
    time?: string
  ) => Promise<void>;
}

/** Sending the evaluator's free slots to the applicant, who picks one.
 *  Slots are keyed "date|time". */
export interface SlotSender {
  editingStage: string | null;
  /** Opens the sender with every free slot ticked. */
  open: (stageType: string) => void;
  close: () => void;
  ticked: string[];
  toggle: (key: string) => void;
  mode: "in_person" | "online";
  setMode: Dispatch<SetStateAction<"in_person" | "online">>;
  location: string;
  setLocation: Dispatch<SetStateAction<string>>;
  meetingLink: string;
  setMeetingLink: Dispatch<SetStateAction<string>>;
  sending: boolean;
  error: string | null;
  send: () => Promise<void>;
}
