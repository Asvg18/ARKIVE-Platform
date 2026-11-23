import { useEffect, useRef, useState, type ReactNode } from "react";
import { apiFetch, ApiError } from "../../../../../shared/api/client";
import type { JDExtractionResponse } from "../../../../../shared/api/pipeline";
import { shownText } from "../../../../../shared/lib/displayText";
import { Button } from "../../../../../shared/ui/Button";
import {
  ArrowRightIcon,
  CheckIcon,
  InfoIcon,
  PencilIcon,
  SparklesIcon,
  UploadIcon,
} from "../../../../../shared/ui/icons";
import { Alert } from "../../../../../shared/ui/Alert";
import { JdDropZone, JdFileRow } from "../../components/JdFileInput";
import { formatSize, jdFileProblem } from "../../../model/jdFile";
import type { Source } from "./builderModel";
import { StepFrame } from "./wizard";

export function DescriptionStep({
  title,
  source,
  onSourceChange,
  file,
  extractedFile,
  token,
  onSelect,
  onExtracted,
  onContinue,
  onManual,
  onBack,
}: {
  title: string;
  source: Source;
  onSourceChange: (s: Source) => void;
  file: File | null;
  extractedFile: File | null;
  token: string | null;
  onSelect: (f: File | null) => void;
  onExtracted: (file: File, result: JDExtractionResponse) => void;
  onContinue: () => void;
  onManual: () => void;
  onBack: () => void;
}) {
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  /** A refusal is a different thing from a failure, and reads differently:
   *  the machinery worked, the document is wrong. Held separately so the
   *  UI can say so and point at the other path rather than offering a
   *  retry that will fail identically. */
  const [rejected, setRejected] = useState<{ message: string; reason: string } | null>(null);

  const alreadyRead = file != null && file === extractedFile;

  // The stepper can take HR back to the title mid-read; a result landing
  // after that must not pull them forward to a step they walked away from.
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  function pick(next: File | undefined) {
    if (!next) return;
    const why = jdFileProblem(next);
    setProblem(why);
    setRejected(null);
    setError(null);
    if (!why) onSelect(next);
  }

  async function handleExtract() {
    if (!file) return;
    setExtracting(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("job_title", title);
      formData.append("jd_file", file);
      const result = await apiFetch<JDExtractionResponse>("/hr/requisitions/extract-jd", {
        method: "POST",
        token,
        body: formData,
      });
      if (alive.current) onExtracted(file, result);
    } catch (err) {
      if (!alive.current) return;
      const detail = err instanceof ApiError ? (err.detail as Record<string, unknown> | undefined) : undefined;
      if (detail && detail.code === "not_a_job_description") {
        setRejected({
          // the reading's own words: what the file appears to be, and why
          message: shownText(String(detail.message ?? "That file is not a job description.")),
          reason: shownText(String(detail.reason ?? "")),
        });
        setError(null);
      } else {
        setError(err instanceof ApiError ? err.message : "Couldn't read the document. You can fill in the fields manually.");
        setRejected(null);
      }
    } finally {
      if (alive.current) setExtracting(false);
    }
  }

  let actions: ReactNode;
  if (source === "manual") {
    actions = (
      <Button variant="primary" onClick={onManual}>
        Continue to the form
        <ArrowRightIcon width={15} height={15} aria-hidden="true" />
      </Button>
    );
  } else if (alreadyRead && !extracting) {
    actions = (
      <>
        <Button variant="ghost" onClick={handleExtract}>
          Read it again
        </Button>
        <Button variant="primary" onClick={onContinue}>
          Continue
          <ArrowRightIcon width={15} height={15} aria-hidden="true" />
        </Button>
      </>
    );
  } else {
    actions = (
      <Button variant="primary" disabled={!file || extracting} onClick={handleExtract}>
        <SparklesIcon width={15} height={15} aria-hidden="true" />
        {extracting ? "Reading the document…" : "Read the document"}
      </Button>
    );
  }

  return (
    <StepFrame
      title="Add the job description"
      sub="Upload the PDF to have the details drafted for you, or write them yourself. Either way, every field stays editable on the next step."
      back={
        <Button variant="secondary" onClick={onBack} disabled={extracting}>
          Back
        </Button>
      }
      actions={actions}
    >
      {/* The manual path used to exist only as a rescue after a failed
          extraction, which framed it as what you do when the product
          breaks. It is a legitimate first choice: HR often writes a
          posting from scratch, and forcing them to find a PDF first —
          or to trigger an error on purpose — was the long way round. */}
      <div className="ark-choices" role="radiogroup" aria-label="Where the details come from">
        <SourceChoice
          checked={source === "upload"}
          disabled={extracting}
          onSelect={() => onSourceChange("upload")}
          icon={<UploadIcon width={18} height={18} />}
          title="Upload the JD as a PDF"
          description="ARKIVE reads the document and drafts the fields for you."
        />
        <SourceChoice
          checked={source === "manual"}
          disabled={extracting}
          onSelect={() => onSourceChange("manual")}
          icon={<PencilIcon width={17} height={17} />}
          title="Type the details myself"
          description="Go straight to the form and write the description, qualifications and requirements."
        />
      </div>

      {source === "upload" && !file && <JdDropZone onPick={pick} />}

      {source === "upload" && file && (
        <JdFileRow
          file={file}
          busy={extracting}
          tone={extracting ? "busy" : alreadyRead ? "done" : undefined}
          meta={
            extracting ? (
              "Reading the document…"
            ) : alreadyRead ? (
              <>
                <CheckIcon width={12} height={12} aria-hidden="true" />
                Details drafted from this file
              </>
            ) : (
              `${formatSize(file.size)} · Ready to extract`
            )
          }
          onPick={pick}
          onRemove={() => {
            onSelect(null);
            setRejected(null);
            setError(null);
          }}
        />
      )}

      {source === "upload" && extracting && file && (
        <p className="ark-wizard__aside-note" aria-live="polite">
          Drafting the department, description, qualifications and requirements from {file.name}.
          This can take a moment.
        </p>
      )}

      {source === "upload" && problem && <Alert tone="danger" title={problem} />}

      {/* A refusal, not a failure. The extractor worked; the document is
          wrong. So it says what the file looked like instead, and offers
          the only two things that actually help — a different file, or
          the manual path — rather than a retry that would fail the same
          way. */}
      {source === "upload" && rejected && (
        <Alert
          tone="warning"
          title={rejected.message}
          action={
            <Button variant="secondary" size="sm" onClick={onManual}>
              Type the details myself instead
            </Button>
          }
        >
          {rejected.reason && <p className="ark-alert__body">{rejected.reason}</p>}
          <p className="ark-alert__body">
            This matters beyond the form: whatever is saved here is the text every applicant&rsquo;s match score
            is measured against.
          </p>
        </Alert>
      )}

      {source === "manual" && (
        <p className="ark-callout">
          <InfoIcon width={15} height={15} aria-hidden="true" />
          <span>
            You&rsquo;ll write the description, qualifications and requirements on the next step. They&rsquo;re
            what each applicant&rsquo;s match score is measured against, so the more specific they are, the
            better the matching works.
          </span>
        </p>
      )}

      {error && (
        <Alert
          tone="danger"
          title={error}
          action={
            <Button variant="secondary" size="sm" onClick={onManual}>
              Continue and fill in manually
            </Button>
          }
        />
      )}
    </StepFrame>
  );
}

function SourceChoice({
  checked,
  disabled,
  onSelect,
  icon,
  title,
  description,
}: {
  checked: boolean;
  disabled?: boolean;
  onSelect: () => void;
  icon: ReactNode;
  title: string;
  description: string;
}) {
  return (
    <button type="button" role="radio" aria-checked={checked} disabled={disabled} className="ark-choice" onClick={onSelect}>
      <span className="ark-choice__icon">{icon}</span>
      <span className="ark-choice__text">
        <span className="ark-choice__title">{title}</span>
        <span className="ark-choice__desc">{description}</span>
      </span>
      <span className="ark-choice__radio" aria-hidden="true" />
    </button>
  );
}
