/** Examinations: schedules, sessions and bookings. */

import type { StageType } from "./applications";

export interface ExaminationSchedule {
  date: string;
  time: string;
  /** End of the session's window, when the applicant booked a session. */
  end_time?: string | null;
  location: string;
}

export interface ExamBookingCandidateSlot {
  id: number;
  date: string;
  time: string;
  location: string;
}

export interface ExamBooking {
  id: number;
  proposed_slot_id: number;
  candidate_slots: ExamBookingCandidateSlot[];
}

export interface ExaminationEntry {
  label: string;
  status: string;
  schedule: ExaminationSchedule | null;
  /** "session": a seat in one of the job's sessions; "typed": a time HR
   *  typed by hand before sessions replaced that (it can only be moved
   *  into a session now); null: nothing booked yet. */
  schedule_source: "session" | "typed" | null;
  booked_slot_id: number | null;
  /** Whether the applicant could still change it themselves (until 24
   *  hours before the session starts). */
  applicant_can_change: boolean;
  /** Sessions still open for this exam, with a free seat. */
  open_sessions: number;
  /** Set once the applicant said none of the open sessions work. */
  none_work: { note: string | null; at: string } | null;
  score: number | null;
  /** The day the exam was sat, recorded with the score. */
  taken_on?: string | null;
  pending_booking: ExamBooking | null;
}

/** One exam session. `remaining_capacity` is seats left; a session with
 *  any seat taken can't be deleted. */
/** One person holding a seat in a session: a row of HR's roster. */
export interface ExamSessionAttendee {
  application_id: number;
  applicant_name: string;
  avatar_url: string | null;
}

export interface ExamSlot {
  id: number;
  stage_type: string;
  date: string;
  time: string;
  end_time: string | null;
  location: string;
  capacity: number;
  remaining_capacity: number;
  /** Who booked it. */
  booked: ExamSessionAttendee[];
}

/** What "Add sessions" made, and how many it left out because the job
 *  already had that exact session. */
export interface ExamSessionBatchResult {
  created: ExamSlot[];
  skipped: number;
}

/** HR's edit of one session; bookers are told when date, time or place change. */
export interface ExamSessionUpdateRequest {
  date: string;
  start: string;
  end: string;
  location: string;
  seats: number;
}

/** HR's "Add sessions": every date × every time window, same seats and
 *  place for all. */
export interface ExamSessionBatchRequest {
  stage_type: StageType;
  dates: string[];
  windows: { start: string; end: string }[];
  seats: number;
  location: string;
}

export interface ExamSlotCreateRequest {
  stage_type: StageType;
  date: string;
  time: string;
  location: string;
  capacity: number;
}
