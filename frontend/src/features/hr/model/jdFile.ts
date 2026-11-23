/** Checks and formatting for a job-description PDF chosen in the browser,
 *  shared by Create Job Opening and the Replace dialog. */

/** The extract endpoint's upload ceiling (backend/app/infra/uploads.py,
 *  MAX_UPLOAD_BYTES). Checked here as well so an oversized file is
 *  refused the moment it is dropped, not after it has been uploaded. */
const MAX_JD_BYTES = 10 * 1024 * 1024;

export function formatSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Why a file can't be used, or null if it can. */
export function jdFileProblem(file: File) {
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) return `${file.name} isn't a PDF. Only PDF files can be read.`;
  if (file.size > MAX_JD_BYTES) return `${file.name} is ${formatSize(file.size)}. The limit is 10 MB.`;
  return null;
}
