/** Job openings: the dashboard, creating and reading a job, its
 *  description, pre-screening questions and workflow. */

import type { StageType } from "./applications";

export interface RequisitionSummary {
  id: number;
  title: string;
  department: string;
  active_candidate_count: number;
}

export interface DashboardSummary {
  open_requisitions: number;
  active_candidates: number;
  pending_final_approvals: number;
  avg_time_to_hire_days: number | null;
  requisitions: RequisitionSummary[];
}

export type RequisitionStatus = "draft" | "open" | "closed";

/** One row of GET /hr/requisitions — every job opening whatever its
 *  status, unlike DashboardSummary.requisitions which is open-only. */
export interface RequisitionListItem {
  id: number;
  title: string;
  department: string;
  status: RequisitionStatus;
  application_deadline: string | null;
  active_candidate_count: number;
  /** Candidates still moving through the pipeline — `active` plus
   *  `flagged`, which active_candidate_count leaves out. Zero is what
   *  makes a posting deletable, and deleting is offered here and only
   *  here. */
  in_flight_candidate_count: number;
  /** Every application ever, however it ended. Not a gate: it's the
   *  number the delete confirmation quotes. */
  application_count: number;
}

export type WorkflowPreset = "standard" | "streamlined";

/** A part of the job description the three fixed fields have no place
 *  for (salary, benefits, documents to submit...). Mirrors
 *  backend/app/schemas/job_description.py::JobDescriptionSection. Not
 *  read by the AI match. */
export interface JobDescriptionSection {
  title: string;
  content: string;
}

/** GET /hr/requisitions/duplicate-check — a live job with this title in
 *  this department, checked while HR types the department. */
export interface DuplicateJobCheck {
  duplicate: boolean;
  message: string | null;
}

export interface RequisitionCreateRequest {
  title: string;
  department: string;
  description: string | null;
  qualifications: string | null;
  requirements: string | null;
  additional_sections: JobDescriptionSection[];
  jd_filename: string | null;
  /** The id extract-jd returned for the PDF, so version 1 keeps the
   *  document itself. Null when the details were typed by hand. */
  jd_upload_id: string | null;
  application_deadline: string | null;
  /** Used only when no workflow_definition is sent. */
  workflow_preset?: WorkflowPreset;
  /** The stages Create Job Opening set up. */
  workflow_definition?: string[];
  interview_round_labels?: Record<string, string>;
  examination_labels?: Record<string, string>;
  /** Minutes per interview round. */
  interview_durations?: Record<string, number>;
  pre_screening_questions?: PreScreeningQuestion[];
  publish: boolean;
}

export interface RequisitionDetail {
  id: number;
  title: string;
  department: string;
  description: string | null;
  qualifications: string | null;
  requirements: string | null;
  additional_sections: JobDescriptionSection[];
  jd_filename: string | null;
  application_deadline: string | null;
  status: RequisitionStatus;
  workflow_definition: StageType[];
  interview_round_labels: Record<string, string> | null;
  examination_labels: Record<string, string> | null;
  /** Minutes per interview round in the workflow — saved, else the default. */
  interview_durations: Record<string, number>;
  pre_screening_questions: PreScreeningQuestion[];
  active_candidate_count: number;
}

export interface PreScreeningQuestion {
  id: string;
  text: string;
  required: boolean;
}

export interface JDExtractionResult {
  department: string;
  description: string;
  qualifications: string;
  requirements: string;
  additional_sections: JobDescriptionSection[];
}

/** What POST /hr/requisitions/extract-jd returns: the fields, plus an id
 *  for the PDF they were read from, which the server now keeps. */
export interface JDExtractionResponse extends JDExtractionResult {
  jd_upload_id: string | null;
}

export interface WorkflowUpdateRequest {
  stages: StageType[];
  interview_round_labels?: Record<string, string>;
  examination_labels?: Record<string, string>;
  /** Minutes per interview round. */
  interview_durations?: Record<string, number>;
}

/** One finding from POST /hr/requisitions/validate-workflow — the same
 *  app.core.workflow_rules the save enforces, surfaced live so the builder
 *  shows a rule before it refuses one. `error` blocks the save; `warning`
 *  is a legal-but-probably-unintended shape (e.g. no AI Pre-Screening). */
export interface WorkflowIssue {
  severity: "error" | "warning";
  code: string;
  message: string;
}

export interface WorkflowValidationResponse {
  issues: WorkflowIssue[];
}
