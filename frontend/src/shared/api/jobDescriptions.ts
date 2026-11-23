import { openFile } from "./client";
import type { JobDescriptionSection, RequisitionStatus } from "./pipeline";

/** Mirrors backend/app/schemas/job_description.py -- one version of a
 *  job opening's description. See models/job_description_version.py for
 *  why versions exist. */
export interface JobDescriptionVersion {
  id: number;
  requisition_id: number;
  job_title: string;
  department: string;
  requisition_status: RequisitionStatus;
  version: number;
  is_current: boolean;
  original_filename: string | null;
  /** False when typed by hand, or added before documents were kept. */
  has_file: boolean;
  file_size: number | null;
  uploaded_by_name: string | null;
  created_at: string;
  replaced_at: string | null;
  change_note: string | null;
  /** Applicants whose stored match score was measured against this version. */
  scored_count: number;
}

export interface JobDescriptionVersionDetail extends JobDescriptionVersion {
  description: string | null;
  qualifications: string | null;
  requirements: string | null;
  additional_sections: JobDescriptionSection[];
}

export interface JobDescriptionReplaceRequest {
  description: string | null;
  qualifications: string | null;
  requirements: string | null;
  additional_sections: JobDescriptionSection[];
  jd_upload_id: string | null;
  jd_filename: string | null;
  change_note: string | null;
  /** The job's title, typed by HR to confirm. Checked by the server too. */
  confirm_title: string;
}

/** An in-place edit from the job opening's page. Only accepted while the
 *  job has no active candidates; answered with the updated job. */
export interface JobDescriptionEditRequest {
  description: string | null;
  qualifications: string | null;
  requirements: string | null;
  additional_sections: JobDescriptionSection[];
  change_note: string | null;
}

/** Opens a version's PDF (an authenticated, non-JSON GET) in a new tab. */
export function openJobDescriptionFile(versionId: number, token: string | null): Promise<void> {
  return openFile(`/hr/job-descriptions/${versionId}/file`, token, "Could not open the job description document.");
}
