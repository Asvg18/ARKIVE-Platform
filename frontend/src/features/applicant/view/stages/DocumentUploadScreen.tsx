import { useState } from "react";
import type { ApplicationDetail } from "../../../../shared/api/applicant";
import { CheckIcon } from "../../../../shared/ui/icons";
import { EMPTY_EDITABLE, toEditable, type EditableResume } from "./document-upload/resumeModel";
import { STEPS } from "./document-upload/uploadFlow";
import { UploadStep } from "./document-upload/UploadStep";
import { ReviewSubmitStep } from "./document-upload/ReviewSubmitStep";

/**
 * The document-upload flow: upload a real PDF, a real GPT-4o-mini call normalizes it into a standardized
 * profile (POST /applicant/resume/extract), the applicant reviews/edits it,
 * and submitting persists the real file plus the (possibly-edited)
 * structured data together (POST .../document-upload). The cover
 * letter is a plain optional textarea, no AI.
 */
export function DocumentUploadScreen({
  application,
  token,
  onAdvance,
}: {
  application: ApplicationDetail;
  token: string | null;
  onAdvance: (updated: ApplicationDetail) => void;
}) {
  const [step, setStep] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [resume, setResume] = useState<EditableResume | null>(null);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 20, flexWrap: "wrap" }}>
        {STEPS.map((stepLabel, i) => (
          <div key={stepLabel} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div
              style={{
                width: 22,
                height: 22,
                borderRadius: "50%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
                background: i < step ? "var(--success-text)" : i === step ? "var(--accent)" : "var(--surface-bg-alt)",
                color: i <= step ? "white" : "var(--ink-400)",
                fontSize: "var(--text-2xs)",
                fontWeight: 700,
              }}
            >
              {i < step ? <CheckIcon width={12} height={12} /> : i + 1}
            </div>
            <span
              style={{
                fontFamily: "var(--arkive-font)",
                fontSize: "var(--text-xs)",
                fontWeight: i === step ? 700 : 600,
                color: i <= step ? "var(--ink-900)" : "var(--ink-400)",
                whiteSpace: "nowrap",
              }}
            >
              {stepLabel}
            </span>
            {i < STEPS.length - 1 && <span style={{ color: "var(--surface-border)", margin: "0 4px" }}>&rarr;</span>}
          </div>
        ))}
      </div>

      {step === 0 && (
        <UploadStep
          file={file}
          token={token}
          onSelect={setFile}
          onExtracted={(result) => {
            setResume(toEditable(result));
            setStep(1);
          }}
          onSkip={() => {
            setResume(EMPTY_EDITABLE);
            setStep(1);
          }}
        />
      )}
      {step === 1 && file && resume && (
        <ReviewSubmitStep
          application={application}
          file={file}
          resume={resume}
          onChange={setResume}
          token={token}
          onBack={() => setStep(0)}
          onAdvance={onAdvance}
        />
      )}
    </div>
  );
}
