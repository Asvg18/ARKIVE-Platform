import { useId, useState } from "react";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { JobDescriptionEditRequest } from "../../../../shared/api/jobDescriptions";
import type { JobDescriptionSection, RequisitionDetail } from "../../../../shared/api/pipeline";
import { Alert } from "../../../../shared/ui/Alert";
import { Button } from "../../../../shared/ui/Button";
import { PencilIcon } from "../../../../shared/ui/icons";
import { JobSectionsEditor, JobSectionsView } from "./JobDescriptionSections";
import { cleanSections, sameSections } from "../../model/jobSections";
import { ReviewField } from "./ReplaceJobDescriptionDialog";

type Fields = { description: string; qualifications: string; requirements: string };

// The two list sections are what the AI match checks line by line
// (skill_matching._chunk_jd_requirements), so the hint says so -- it is
// the one thing about the format that changes how a candidate is read.
const FIELDS: { key: keyof Fields; label: string; rows: number; hint?: string }[] = [
  { key: "description", label: "Role description", rows: 5 },
  {
    key: "qualifications",
    label: "Qualifications",
    rows: 5,
    hint: "One item per line. The match score checks each line against the resume.",
  },
  {
    key: "requirements",
    label: "Requirements",
    rows: 5,
    hint: "One item per line. The match score checks each line against the resume.",
  },
];

const same = (a: string | null | undefined, b: string | null | undefined) => (a ?? "").trim() === (b ?? "").trim();

function fieldsOf(job: RequisitionDetail): Fields {
  return {
    description: job.description ?? "",
    qualifications: job.qualifications ?? "",
    requirements: job.requirements ?? "",
  };
}

/** The Job posting panel on a job opening's page, editable in place until
 *  someone applies.
 *
 *  Locked by the same rule as the stage order — any active candidate —
 *  and enforced by the server, not only hidden here. A save is a new
 *  version in the job description history, exactly as a replacement from
 *  the history on Create Job Opening is: the next applicant is matched
 *  against the new text, and nobody already scored is re-scored. */
export function JobPostingPanel({
  job,
  locked,
  note,
  token,
  onSaved,
}: {
  job: RequisitionDetail;
  locked: boolean;
  /** Where the posting is being read, if anywhere. */
  note: string;
  token: string | null;
  onSaved: (updated: RequisitionDetail) => void;
}) {
  const [draft, setDraft] = useState<Fields | null>(null);
  const [sections, setSections] = useState<JobDescriptionSection[]>([]);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const reasonId = useId();

  const current = fieldsOf(job);
  const currentSections = job.additional_sections ?? [];
  const editing = draft !== null && !locked;
  const sectionsChanged = editing && !sameSections(sections, currentSections);
  const changed = draft ? FIELDS.filter((f) => !same(draft[f.key], current[f.key])) : [];
  const anyChange = changed.length > 0 || sectionsChanged;
  const empty = draft ? FIELDS.every((f) => !draft[f.key].trim()) : false;

  function startEditing() {
    setDraft(current);
    setSections(currentSections);
    setReason("");
    setError(null);
    setSaved(false);
  }

  function cancel() {
    setDraft(null);
    setError(null);
  }

  async function save() {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      const body: JobDescriptionEditRequest = {
        description: draft.description.trim() || null,
        qualifications: draft.qualifications.trim() || null,
        requirements: draft.requirements.trim() || null,
        additional_sections: cleanSections(sections),
        change_note: reason.trim() || null,
      };
      const updated = await apiFetch<RequisitionDetail>(`/hr/requisitions/${job.id}/job-description`, {
        method: "PATCH",
        token,
        body,
      });
      setDraft(null);
      setSaved(true);
      onSaved(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The job description could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="ark-panel" aria-labelledby="job-posting-heading">
      <div className="ark-panel__head">
        <div>
          <h2 id="job-posting-heading" className="ark-panel__title">
            {editing ? "Edit job posting" : "Job posting"}
          </h2>
          <p className="ark-panel__sub">
            {editing
              ? "Saved as a new version. Applicants from now on are matched against it."
              : locked
                ? `${note} Locked while candidates are active.`
                : note}
          </p>
        </div>
        {!editing && !locked && (
          <Button variant="secondary" size="sm" onClick={startEditing}>
            <PencilIcon width={13} height={13} aria-hidden="true" />
            Edit
          </Button>
        )}
      </div>

      <div className="ark-panel__body">
        {editing ? (
          <div className="ark-fields">
            {FIELDS.map((f) => (
              <ReviewField
                key={f.key}
                label={f.label}
                rows={f.rows}
                hint={f.hint}
                value={draft[f.key]}
                changed={!same(draft[f.key], current[f.key])}
                onChange={(value) => setDraft((d) => (d ? { ...d, [f.key]: value } : d))}
              />
            ))}
            <JobSectionsEditor sections={sections} changed={sectionsChanged} onChange={setSections} />
            <div className="ark-field">
              <div className="ark-field__label-row">
                <label className="ark-field__label" htmlFor={reasonId}>
                  Reason for the change
                  <span className="ark-field__req">Optional</span>
                </label>
              </div>
              <input
                id={reasonId}
                className="ark-input"
                maxLength={500}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. Department added Python to the requirements"
              />
              <p className="ark-field__hint">Shown in the job description history next to this version.</p>
            </div>
            {empty && (
              <Alert
                tone="warning"
                title="A job description needs a role description, qualifications or requirements filled in."
              />
            )}
            {error && <Alert tone="danger" title={error} />}
          </div>
        ) : (
          <div className="ark-jd-text">
            {saved && (
              <Alert
                tone="success"
                title="Saved. Applicants from now on are matched against this text."
              />
            )}
            <PostingField label="Role description" text={job.description} />
            <PostingField label="Qualifications" text={job.qualifications} />
            <PostingField label="Requirements" text={job.requirements} />
            <JobSectionsView sections={currentSections} />
          </div>
        )}
      </div>

      {editing && (
        <div className="ark-panel__foot ark-panel__foot--actions">
          {!anyChange && <span className="ark-wizard__note">Nothing has changed yet</span>}
          <Button variant="secondary" onClick={cancel} disabled={saving}>
            Cancel
          </Button>
          <Button variant="primary" onClick={save} disabled={saving || !anyChange || empty}>
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </div>
      )}
    </section>
  );
}

function PostingField({ label, text }: { label: string; text: string | null }) {
  const body = text?.trim();
  return (
    <div>
      <p className="ark-jd-text__label">{label}</p>
      {body ? (
        <p className="ark-jd-text__body">{body}</p>
      ) : (
        <p className="ark-jd-text__body" data-empty="">
          Not provided
        </p>
      )}
    </div>
  );
}
