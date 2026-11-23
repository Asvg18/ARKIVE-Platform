/** Mirrors backend/app/schemas/application_document.py -- a supplemental
 * document (reference letter, updated portfolio, etc.) added after the
 * initial document_upload submission. Shared between the applicant's
 * own ApplicationDetail and HR's CandidateProfile, same reasoning as
 * ApplicationResumeRead in ./resume.ts. */
export interface ApplicationDocument {
  id: number;
  label: string;
  original_filename: string;
  created_at: string;
}
