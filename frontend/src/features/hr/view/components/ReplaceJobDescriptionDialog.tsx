import { useEffect, useId, useState, type ReactNode } from "react";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { JDExtractionResponse, JobDescriptionSection } from "../../../../shared/api/pipeline";
import { shownText } from "../../../../shared/lib/displayText";
import type {
  JobDescriptionReplaceRequest,
  JobDescriptionVersion,
  JobDescriptionVersionDetail,
} from "../../../../shared/api/jobDescriptions";
import { Alert } from "../../../../shared/ui/Alert";
import { Button } from "../../../../shared/ui/Button";
import { Modal } from "../../../../shared/ui/Modal";
import { ArrowRightIcon, CheckIcon, PencilIcon, SparklesIcon, UploadIcon } from "../../../../shared/ui/icons";
import { JdDropZone, JdFileRow } from "./JdFileInput";
import { JobSectionsEditor } from "./JobDescriptionSections";
import { cleanSections, sameSections } from "../../model/jobSections";
import { formatSize, jdFileProblem } from "../../model/jdFile";

type Stage = "source" | "review" | "confirm";
type Source = "upload" | "manual";
type Fields = { description: string; qualifications: string; requirements: string };

const FIELDS: { key: keyof Fields; label: string; rows: number }[] = [
  { key: "description", label: "Role description", rows: 5 },
  { key: "qualifications", label: "Qualifications", rows: 4 },
  { key: "requirements", label: "Requirements", rows: 4 },
];

const same = (a: string | null | undefined, b: string | null | undefined) => (a ?? "").trim() === (b ?? "").trim();

/** Replaces the job description in force for one job opening, in three
 *  steps: where the new text comes from (a new PDF read by the AI, or an
 *  edit of the current text), a review of every field with what changed
 *  marked, and a confirmation that spells out what happens to applicants
 *  already scored and asks for the job's title to be typed.
 *
 *  The typed title is the brake: this text is the basis of every future
 *  match score on the job, so a replacement nobody meant is expensive to
 *  notice and to undo. The server checks it too. */
export function ReplaceJobDescriptionDialog({
  current,
  token,
  onClose,
  onReplaced,
}: {
  /** The version in force now — the row Replace was chosen from. */
  current: JobDescriptionVersion;
  token: string | null;
  onClose: () => void;
  onReplaced: (version: JobDescriptionVersion, previous: JobDescriptionVersion) => void;
}) {
  const [stage, setStage] = useState<Stage>("source");
  const [source, setSource] = useState<Source>("upload");
  const [currentText, setCurrentText] = useState<Fields | null>(null);
  const [currentSections, setCurrentSections] = useState<JobDescriptionSection[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [readFile, setReadFile] = useState<File | null>(null);
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [rejected, setRejected] = useState<{ message: string; reason: string } | null>(null);

  const [draft, setDraft] = useState<Fields>({ description: "", qualifications: "", requirements: "" });
  const [draftSections, setDraftSections] = useState<JobDescriptionSection[]>([]);
  const [note, setNote] = useState("");
  const [typedTitle, setTypedTitle] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const noteId = useId();
  const confirmId = useId();

  // The text in force now, for the "edit" path and for marking what
  // changed. Read from the version itself rather than the job, so it is
  // exactly what this history row says is current.
  useEffect(() => {
    apiFetch<JobDescriptionVersionDetail>(`/hr/job-descriptions/${current.id}`, { token })
      .then((detail) => {
        setCurrentText({
          description: detail.description ?? "",
          qualifications: detail.qualifications ?? "",
          requirements: detail.requirements ?? "",
        });
        setCurrentSections(detail.additional_sections ?? []);
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Could not load the current text."));
  }, [current.id, token]);

  const fromDocument = source === "upload" && file != null && file === readFile;
  const changed = currentText ? FIELDS.filter((f) => !same(draft[f.key], currentText[f.key])) : [];
  const sectionsChanged = currentText != null && !sameSections(draftSections, currentSections);
  const changedLabels = [...changed.map((f) => f.label.toLowerCase()), ...(sectionsChanged ? ["other sections"] : [])];
  const nothingToReplace = changedLabels.length === 0 && !fromDocument;
  const titleMatches = typedTitle.trim().toLowerCase() === current.job_title.trim().toLowerCase();
  const next = current.version + 1;

  function pick(next: File | undefined) {
    if (!next) return;
    const why = jdFileProblem(next);
    setProblem(why);
    setRejected(null);
    setError(null);
    if (!why) setFile(next);
  }

  async function extract() {
    if (!file) return;
    setExtracting(true);
    setError(null);
    setRejected(null);
    try {
      const formData = new FormData();
      formData.append("job_title", current.job_title);
      formData.append("jd_file", file);
      const result = await apiFetch<JDExtractionResponse>("/hr/requisitions/extract-jd", {
        method: "POST",
        token,
        body: formData,
      });
      setDraft({ description: result.description, qualifications: result.qualifications, requirements: result.requirements });
      setDraftSections(result.additional_sections ?? []);
      setReadFile(file);
      setUploadId(result.jd_upload_id);
      setStage("review");
    } catch (err) {
      const detail = err instanceof ApiError ? (err.detail as Record<string, unknown> | undefined) : undefined;
      if (detail && detail.code === "not_a_job_description") {
        setRejected({
          // the reading's own words: what the file appears to be, and why
          message: shownText(String(detail.message ?? "That file is not a job description.")),
          reason: shownText(String(detail.reason ?? "")),
        });
      } else {
        setError(err instanceof ApiError ? err.message : "The document could not be read.");
      }
    } finally {
      setExtracting(false);
    }
  }

  async function replace() {
    setSubmitting(true);
    setError(null);
    try {
      const body: JobDescriptionReplaceRequest = {
        description: draft.description.trim() || null,
        qualifications: draft.qualifications.trim() || null,
        requirements: draft.requirements.trim() || null,
        additional_sections: cleanSections(draftSections),
        jd_upload_id: fromDocument ? uploadId : null,
        jd_filename: fromDocument ? file.name : null,
        change_note: note.trim() || null,
        confirm_title: typedTitle,
      };
      const created = await apiFetch<JobDescriptionVersion>(
        `/hr/requisitions/${current.requisition_id}/job-description`,
        { method: "POST", token, body },
      );
      onReplaced(created, current);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The job description could not be replaced.");
      setSubmitting(false);
    }
  }

  let body: ReactNode;
  let footer: ReactNode;

  if (stage === "source") {
    body = (
      <>
        <div className="ark-choices" role="radiogroup" aria-label="Where the new text comes from">
          <ChoiceCard
            checked={source === "upload"}
            disabled={extracting}
            onSelect={() => setSource("upload")}
            icon={<UploadIcon width={18} height={18} />}
            title="Upload a new PDF"
            description="ARKIVE reads the revised document and drafts the fields for you to check."
          />
          <ChoiceCard
            checked={source === "manual"}
            disabled={extracting}
            onSelect={() => setSource("manual")}
            icon={<PencilIcon width={17} height={17} />}
            title="Edit the current text"
            description="For a small change: start from the text in force now and edit it."
          />
        </div>

        {source === "upload" && !file && <JdDropZone onPick={pick} />}
        {source === "upload" && file && (
          <JdFileRow
            file={file}
            busy={extracting}
            tone={extracting ? "busy" : undefined}
            meta={extracting ? "Reading the document…" : `${formatSize(file.size)} · Ready to extract`}
            onPick={pick}
            onRemove={() => {
              setFile(null);
              setRejected(null);
            }}
          />
        )}
        {source === "upload" && problem && <Alert tone="danger" title={problem} />}
        {source === "upload" && rejected && (
          <Alert tone="warning" title={rejected.message}>
            {rejected.reason && <p className="ark-alert__body">{rejected.reason}</p>}
          </Alert>
        )}
        {loadError && <Alert tone="danger" title={loadError} />}
        {error && <Alert tone="danger" title={error} />}
      </>
    );
    footer = (
      <>
        <Button variant="secondary" onClick={onClose} disabled={extracting}>
          Cancel
        </Button>
        <div className="ark-wizard__foot-end">
          {source === "upload" ? (
            <Button variant="primary" disabled={!file || extracting} onClick={extract}>
              <SparklesIcon width={15} height={15} aria-hidden="true" />
              {extracting ? "Reading the document…" : "Read the document"}
            </Button>
          ) : (
            <Button
              variant="primary"
              disabled={!currentText}
              onClick={() => {
                if (currentText) setDraft(currentText);
                setDraftSections(currentSections);
                setStage("review");
              }}
            >
              Continue
              <ArrowRightIcon width={15} height={15} aria-hidden="true" />
            </Button>
          )}
        </div>
      </>
    );
  } else if (stage === "review") {
    body = (
      <div className="ark-fields">
        {FIELDS.map((f) => {
          const isChanged = currentText != null && !same(draft[f.key], currentText[f.key]);
          return (
            <ReviewField
              key={f.key}
              label={f.label}
              rows={f.rows}
              value={draft[f.key]}
              changed={isChanged}
              onChange={(value) => setDraft((d) => ({ ...d, [f.key]: value }))}
            />
          );
        })}
        <JobSectionsEditor sections={draftSections} changed={sectionsChanged} onChange={setDraftSections} />
      </div>
    );
    footer = (
      <>
        <Button variant="secondary" onClick={() => setStage("source")}>
          Back
        </Button>
        <div className="ark-wizard__foot-end">
          {nothingToReplace && <span className="ark-wizard__note">Nothing has changed yet</span>}
          <Button variant="primary" disabled={nothingToReplace} onClick={() => setStage("confirm")}>
            Continue
            <ArrowRightIcon width={15} height={15} aria-hidden="true" />
          </Button>
        </div>
      </>
    );
  } else {
    const scored = current.scored_count;
    body = (
      <>
        <div className="ark-replace-summary">
          <p className="ark-replace-summary__title">
            Version {next} replaces version {current.version} for {current.job_title}
          </p>
          <ul className="ark-replace-summary__list">
            <li>
              {scored === 0 ? (
                <>No applicant has been scored against version {current.version} yet.</>
              ) : (
                <>
                  <strong>
                    {scored} applicant{scored === 1 ? "" : "s"} already scored
                  </strong>{" "}
                  {scored === 1 ? "keeps their score" : "keep their scores"}, measured against version{" "}
                  {current.version}. No one is re-scored.
                </>
              )}
            </li>
            <li>Applicants scored from now on are measured against version {next}.</li>
            <li>
              Version {current.version} stays in this history with its text
              {current.has_file ? " and document" : ""}, so what anyone was scored against can always be checked.
            </li>
          </ul>
          <p className="ark-replace-summary__changes">
            {fromDocument ? <>New document: {file.name}. </> : null}
            {changedLabels.length > 0 ? `Changed: ${changedLabels.join(", ")}.` : "The text is unchanged."}
          </p>
        </div>

        <div className="ark-fields" style={{ marginTop: "var(--space-5)" }}>
          <div className="ark-field">
            <div className="ark-field__label-row">
              <label className="ark-field__label" htmlFor={noteId}>
                Reason for the change
                <span className="ark-field__req">Optional</span>
              </label>
            </div>
            <textarea
              id={noteId}
              className="ark-input"
              rows={2}
              maxLength={500}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. Department added Python to the requirements"
            />
            <p className="ark-field__hint">Shown in the history next to this version.</p>
          </div>
          <div className="ark-field">
            <div className="ark-field__label-row">
              <label className="ark-field__label" htmlFor={confirmId}>
                Type <span className="ark-replace-summary__typed">{current.job_title}</span> to confirm
              </label>
              {titleMatches && (
                <span className="ark-field__flag ark-field__flag--ok">
                  <CheckIcon width={12} height={12} aria-hidden="true" />
                  Matches
                </span>
              )}
            </div>
            <input
              id={confirmId}
              className="ark-input"
              value={typedTitle}
              onChange={(e) => setTypedTitle(e.target.value)}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
        </div>
        {error && <Alert tone="danger" title={error} />}
      </>
    );
    footer = (
      <>
        <Button variant="secondary" onClick={() => setStage("review")} disabled={submitting}>
          Back
        </Button>
        <div className="ark-wizard__foot-end">
          <Button variant="primary" disabled={!titleMatches || submitting} onClick={replace}>
            {submitting ? "Replacing…" : "Replace job description"}
          </Button>
        </div>
      </>
    );
  }

  const subs: Record<Stage, ReactNode> = {
    source: `${current.job_title} · version ${current.version} is in force now`,
    review: fromDocument ? (
      <>
        Drafted from <strong className="ark-wizard__file">{file.name}</strong>. Fields that differ from version{" "}
        {current.version} are marked.
      </>
    ) : (
      `Edit the text. Fields that differ from version ${current.version} are marked.`
    ),
    confirm: "Check what happens, then confirm.",
  };
  const titles: Record<Stage, string> = {
    source: "Replace job description",
    review: "Review the new text",
    confirm: "Confirm the replacement",
  };

  return (
    <Modal
      open
      title={titles[stage]}
      sub={subs[stage]}
      aside={<span className="ark-modal__step">Step {stage === "source" ? 1 : stage === "review" ? 2 : 3} of 3</span>}
      footer={footer}
      busy={extracting || submitting}
      onClose={onClose}
    >
      <div key={stage} className="ark-wizard__stage">
        {body}
      </div>
    </Modal>
  );
}

function ChoiceCard({
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

/** One job-description section as an editable box, marked when it
 *  differs from the text in force. Also used by the job opening page's
 *  in-place edit (JobPostingPanel). */
export function ReviewField({
  label,
  rows,
  value,
  changed,
  hint,
  onChange,
}: {
  label: string;
  rows: number;
  value: string;
  changed: boolean;
  hint?: string;
  onChange: (value: string) => void;
}) {
  const id = useId();
  const hintId = useId();
  return (
    <div className="ark-field">
      <div className="ark-field__label-row">
        <label className="ark-field__label" htmlFor={id}>
          {label}
        </label>
        {changed && <span className="ark-field__flag ark-field__flag--changed">Changed</span>}
      </div>
      <textarea
        id={id}
        className="ark-input"
        rows={rows}
        value={value}
        aria-describedby={hint ? hintId : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      {hint && (
        <p id={hintId} className="ark-field__hint">
          {hint}
        </p>
      )}
    </div>
  );
}
