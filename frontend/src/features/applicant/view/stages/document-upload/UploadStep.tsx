/** Step one: the applicant picks their résumé PDF and it is read into a
 *  profile (POST /applicant/resume/extract). */
import { useState } from "react";
import { AI_REQUEST_TIMEOUT_MS, apiFetch, ApiError } from "../../../../../shared/api/client";
import type { ResumeExtractionResult } from "../../../../../shared/api/resume";
import { Button } from "../../../../../shared/ui/Button";
import { ReadingProgress } from "../../../../../shared/ui/ReadingProgress";
import { UploadIcon } from "../../../../../shared/ui/icons";
import { DONE_PAUSE_MS, READ_EXPECTED_MS, READ_STEPS } from "./uploadFlow";
import { heading, subtext } from "./formStyle";

export function UploadStep({
  file,
  token,
  onSelect,
  onExtracted,
  onSkip,
}: {
  file: File | null;
  token: string | null;
  onSelect: (f: File) => void;
  onExtracted: (result: ResumeExtractionResult) => void;
  onSkip: () => void;
}) {
  const [extracting, setExtracting] = useState(false);
  const [finished, setFinished] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleExtract() {
    if (!file) return;
    setExtracting(true);
    setFinished(false);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("resume_file", file);
      const result = await apiFetch<ResumeExtractionResult>("/applicant/resume/extract", {
        method: "POST",
        token,
        body: formData,
        timeoutMs: AI_REQUEST_TIMEOUT_MS,
      });
      setFinished(true);
      await new Promise((resolve) => window.setTimeout(resolve, DONE_PAUSE_MS));
      onExtracted(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't read your resume. You can fill in the fields manually.");
    } finally {
      setExtracting(false);
    }
  }

  return (
    <div>
      <h2 style={heading}>Upload Your Resume</h2>
      <p style={subtext}>
        Attach your resume as a PDF. ARKIVE reads it and turns it into a standard
        profile. You'll review and can edit every field before it's submitted.
      </p>

      {/* While ARKIVE reads, the reading screen takes the form's place;
          an error brings the form back, with
          the way to fill it in by hand. */}
      {extracting ? (
        <ReadingProgress
          title="Reading your resume"
          steps={READ_STEPS}
          expectedMs={READ_EXPECTED_MS}
          done={finished}
          fileName={file?.name}
        />
      ) : (
        <>
          <label
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 10,
              border: "1.5px dashed var(--surface-border)",
              borderRadius: "var(--radius)",
              padding: "40px 20px",
              marginTop: 20,
              background: "var(--surface-bg)",
              cursor: "pointer",
              textAlign: "center",
            }}
          >
            <UploadIcon width={28} height={28} style={{ color: "var(--accent)" }} />
            <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", fontWeight: 600, color: "var(--ink-900)" }}>
              {file ? file.name : "Click to choose a file, or drag it here"}
            </span>
            <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xs)", color: "var(--ink-400)" }}>PDF only</span>
            <input
              type="file"
              accept=".pdf,application/pdf"
              onChange={(e) => e.target.files?.[0] && onSelect(e.target.files[0])}
              style={{ display: "none" }}
            />
          </label>

          {error && (
            <div style={{ marginTop: 16 }}>
              <p style={{ color: "crimson", fontSize: "var(--text-sm)", margin: 0 }}>{error}</p>
              <Button variant="ghost" onClick={onSkip} style={{ marginTop: 8, padding: "6px 0" }}>
                Continue and fill in manually
              </Button>
            </div>
          )}

          <Button variant="primary" disabled={!file} onClick={handleExtract} style={{ marginTop: 20 }}>
            Read my resume
          </Button>
        </>
      )}
    </div>
  );
}
