import { useEffect, useState } from "react";
import { apiFetch } from "../../../../../shared/api/client";
import type { DuplicateJobCheck, JDExtractionResult } from "../../../../../shared/api/pipeline";
import { Button } from "../../../../../shared/ui/Button";
import { ArrowRightIcon, SparklesIcon } from "../../../../../shared/ui/icons";
import { Alert } from "../../../../../shared/ui/Alert";
import { JobSectionsEditor } from "../../components/JobDescriptionSections";
import { Tag } from "../../../../../shared/ui/Tag";
import type { TextField } from "./builderModel";
import { Field, StepFrame } from "./wizard";

/** The same title already live in this department, asked of the server
 *  as HR types the department (and as soon as the step opens, when the
 *  department was drafted from the PDF) — so it is said here, not only
 *  when the finished job is published. Waits for a pause in typing; the
 *  create route still refuses a duplicate on its own. */
function useDuplicateJob(title: string, department: string, token: string | null): string | null {
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    const t = title.trim();
    const d = department.trim();
    if (!t || !d) {
      setMessage(null);
      return;
    }
    let current = true;
    const timer = window.setTimeout(() => {
      const query = new URLSearchParams({ title: t, department: d });
      apiFetch<DuplicateJobCheck>(`/hr/requisitions/duplicate-check?${query}`, { token })
        .then((result) => {
          if (current) setMessage(result.duplicate ? result.message : null);
        })
        .catch(() => {
          // a failed check says nothing either way; publishing still checks
          if (current) setMessage(null);
        });
    }, 350);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [title, department, token]);
  return message;
}

export function ReviewDetailsStep({
  title,
  token,
  extraction,
  onChange,
  applicationDeadline,
  onDeadlineChange,
  onNext,
  onBack,
  fromUpload,
  fileName,
  missingFromPdf,
}: {
  title: string;
  token: string | null;
  extraction: JDExtractionResult;
  onChange: (e: JDExtractionResult) => void;
  /** Whether these fields came from a PDF or are being written by hand.
   *  The step is otherwise identical, but calling an empty form "Review
   *  Extracted Details" tells HR something was extracted when nothing
   *  was — and the "AI drafted" tag beside it makes that worse. */
  fromUpload: boolean;
  fileName: string | null;
  missingFromPdf: TextField[];
  applicationDeadline: string;
  onDeadlineChange: (v: string) => void;
  onNext: () => void;
  onBack: () => void;
}) {
  function setField<K extends keyof JDExtractionResult>(key: K, value: JDExtractionResult[K]) {
    onChange({ ...extraction, [key]: value });
  }

  /** "Not in the PDF" beside a field the AI came back empty for, until HR
   *  fills it in. */
  function flag(key: TextField) {
    if (!fromUpload || !missingFromPdf.includes(key) || extraction[key].trim() !== "") return undefined;
    return "Not found in the PDF";
  }

  const duplicate = useDuplicateJob(title, extraction.department, token);
  const hasDepartment = extraction.department.trim().length > 0;
  const hasDeadline = applicationDeadline.trim().length > 0;
  const canContinue = hasDepartment && hasDeadline && !duplicate;

  let note: string | undefined;
  if (duplicate) note = "Change the department, or go back and change the title";
  else if (!hasDepartment && !hasDeadline) note = "Add a department and a deadline to continue";
  else if (!hasDepartment) note = "Add a department to continue";
  else if (!hasDeadline) note = "Add a deadline to continue";

  return (
    <StepFrame
      title={fromUpload ? "Review the extracted details" : "Write the job details"}
      sub={
        fromUpload ? (
          <>
            Drafted from <strong className="ark-wizard__file">{fileName ?? "your PDF"}</strong>. Edit anything
            that&rsquo;s wrong or missing.
          </>
        ) : (
          "These are what each applicant's match score is measured against. The more specific, the better the matching."
        )
      }
      aside={
        fromUpload && (
          <Tag tone="green">
            <SparklesIcon width={12} height={12} aria-hidden="true" />
            Auto-drafted
          </Tag>
        )
      }
      back={
        <Button variant="secondary" onClick={onBack}>
          Back
        </Button>
      }
      note={note}
      actions={
        <Button variant="primary" disabled={!canContinue} onClick={onNext}>
          Continue
          <ArrowRightIcon width={15} height={15} aria-hidden="true" />
        </Button>
      }
    >
      <div className="ark-fields">
        <div className="ark-fields ark-fields--2">
          <Field label="Department" required flag={flag("department")}>
            {(id) => (
              <input
                id={id}
                type="text"
                className="ark-input"
                value={extraction.department}
                onChange={(e) => setField("department", e.target.value)}
                placeholder="e.g. College of Engineering"
                aria-invalid={duplicate ? true : undefined}
              />
            )}
          </Field>
          <Field label="Application deadline" required hint="Shown to applicants as “Applications close in N days.”">
            {(id) => (
              <input
                id={id}
                type="date"
                className="ark-input"
                value={applicationDeadline}
                onChange={(e) => onDeadlineChange(e.target.value)}
              />
            )}
          </Field>
        </div>
        {duplicate && <Alert tone="danger" title={duplicate} />}

        <Field label="Role description" flag={flag("description")}>
          {(id) => (
            <textarea
              id={id}
              className="ark-input"
              value={extraction.description}
              onChange={(e) => setField("description", e.target.value)}
              rows={5}
            />
          )}
        </Field>
        <Field label="Qualifications" flag={flag("qualifications")}>
          {(id) => (
            <textarea
              id={id}
              className="ark-input"
              value={extraction.qualifications}
              onChange={(e) => setField("qualifications", e.target.value)}
              rows={4}
            />
          )}
        </Field>
        <Field label="Requirements" flag={flag("requirements")}>
          {(id) => (
            <textarea
              id={id}
              className="ark-input"
              value={extraction.requirements}
              onChange={(e) => setField("requirements", e.target.value)}
              rows={4}
            />
          )}
        </Field>
        <JobSectionsEditor
          sections={extraction.additional_sections}
          onChange={(sections) => setField("additional_sections", sections)}
        />
      </div>
    </StepFrame>
  );
}
