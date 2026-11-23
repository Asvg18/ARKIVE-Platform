import type { JobDescriptionSection } from "./pipeline";

export interface JobListItem {
  id: number;
  title: string;
  department: string;
  description: string | null;
  qualifications: string | null;
  requirements: string | null;
  /** The rest of the posting: salary, benefits, documents to submit... */
  additional_sections: JobDescriptionSection[];
  application_deadline: string | null;
  stage_count: number;
  created_at: string;
}

/** GET /public/jobs. `total` counts every job matching the active
 * filters (not just the returned page); `departments` is the full
 * department set across all open jobs -- not narrowed by the active
 * query, so the filter controls stay stable as the user searches. */
export interface JobListResponse {
  items: JobListItem[];
  total: number;
  departments: string[];
}

export interface JobDetail {
  id: number;
  title: string;
  department: string;
  description: string | null;
  qualifications: string | null;
  requirements: string | null;
  /** The rest of the posting: salary, benefits, documents to submit... */
  additional_sections: JobDescriptionSection[];
  application_deadline: string | null;
  workflow_definition: string[];
  /** The same stages in this job's own words (custom round names). */
  stage_labels?: string[];
  created_at: string;
}
