/** Mirrors backend/app/schemas/interview_report.py. The job opening page
 *  reads this to offer the printable report, or to say who it is still
 *  waiting on; the PDF is built from the same object on the server. */

export interface InterviewReportRound {
  stage_type: string;
  label: string;
  /** Set when one person ran this round for every ranked candidate. */
  evaluator_name: string | null;
}

export interface InterviewReportCell {
  stage_type: string;
  score: number | null;
  /** The form's General Evaluation for this round: Highly Qualified,
   *  Qualified or Not Qualified. */
  tier: string | null;
  tier_label: string | null;
  /** The interviewer's own pick on the form, never derived from the score. */
  recommendation: string | null;
  recommendation_label: string | null;
  evaluator_name: string | null;
  no_scorecard: boolean;
}

export interface InterviewReportEntry {
  rank: number;
  application_id: number;
  applicant_name: string;
  cells: InterviewReportCell[];
  /** (interviewer 1 + interviewer 2 + interviewer 3) / 3 — a plain
   *  average, not the Candidate Profile's 30/30/40 consensus. */
  final_score: number;
  /** A round has no scorecard, so the average is over fewer rounds. */
  partial: boolean;
}

export interface InterviewReport {
  requisition_id: number;
  job_title: string;
  department: string;
  has_interviews: boolean;
  ready: boolean;
  rounds: InterviewReportRound[];
  entries: InterviewReportEntry[];
  pending: { application_id: number; applicant_name: string; waiting_on: string[] }[];
  excluded: { applicant_name: string; reason: string }[];
  generated_at: string;
  filename: string;
}

export const interviewReportPdfPath = (requisitionId: number) =>
  `/hr/requisitions/${requisitionId}/interview-report/pdf`;
