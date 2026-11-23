/** Step two: the applicant checks and edits the read profile, adds an
 *  optional cover letter, and submits both with the file. */
import { useState } from "react";
import { AI_REQUEST_TIMEOUT_MS, apiFetch, ApiError } from "../../../../../shared/api/client";
import type { ApplicationDetail } from "../../../../../shared/api/applicant";
import {
  type ResumeAdditionalSection,
  type ResumeEducationEntry,
  type ResumeExperienceEntry
} from "../../../../../shared/api/resume";
import { Button } from "../../../../../shared/ui/Button";
import { Tag } from "../../../../../shared/ui/Tag";
import { ConfirmDialog } from "../../../../../shared/ui/ConfirmDialog";
import { ReadingProgress } from "../../../../../shared/ui/ReadingProgress";
import { toResult, type EditableResume } from "./resumeModel";
import { DONE_PAUSE_MS, SUBMIT_EXPECTED_MS, SUBMIT_STEPS } from "./uploadFlow";
import { heading, inputStyle, label, subtext, textareaStyle } from "./formStyle";
import { EmptyRow, EntryCard, Field } from "./formParts";

export function ReviewSubmitStep({
  application,
  file,
  resume,
  onChange,
  token,
  onBack,
  onAdvance,
}: {
  application: ApplicationDetail;
  file: File;
  resume: EditableResume;
  onChange: (r: EditableResume) => void;
  token: string | null;
  onBack: () => void;
  onAdvance: (updated: ApplicationDetail) => void;
}) {
  const [letterOfIntent, setLetterOfIntent] = useState("");
  const [confirmingSubmit, setConfirmingSubmit] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function setField<K extends keyof EditableResume>(key: K, value: EditableResume[K]) {
    onChange({ ...resume, [key]: value });
  }

  function updateEducation(index: number, entry: ResumeEducationEntry) {
    const next = [...resume.education];
    next[index] = entry;
    setField("education", next);
  }

  function updateExperience(index: number, entry: ResumeExperienceEntry) {
    const next = [...resume.experience];
    next[index] = entry;
    setField("experience", next);
  }

  function updateSection(index: number, section: ResumeAdditionalSection) {
    const next = [...resume.additional_sections];
    next[index] = section;
    setField("additional_sections", next);
  }

  const canSubmit = resume.full_name.trim().length > 0 && resume.email.trim().length > 0;

  async function handleSubmit() {
    setSubmitting(true);
    setSubmitted(false);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("resume_file", file);
      formData.append("resume_data", JSON.stringify(toResult(resume)));
      if (letterOfIntent.trim()) formData.append("letter_of_intent", letterOfIntent.trim());
      const updated = await apiFetch<ApplicationDetail>(
        `/applicant/applications/${application.id}/document-upload`,
        { method: "POST", token, body: formData, timeoutMs: AI_REQUEST_TIMEOUT_MS }
      );
      setSubmitted(true);
      await new Promise((resolve) => window.setTimeout(resolve, DONE_PAUSE_MS));
      onAdvance(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit your documents.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h2 style={heading}>Review Your Profile</h2>
          <p style={subtext}>Drawn from {file.name}. Edit anything that's incorrect or missing.</p>
        </div>
        <Tag tone="green" dot>
          Extracted
        </Tag>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginTop: 20 }}>
        <Field label="Full Name" value={resume.full_name} onChange={(v) => setField("full_name", v)} />
        <Field label="Email Address" value={resume.email} onChange={(v) => setField("email", v)} />
        <Field label="Phone Number" value={resume.phone} onChange={(v) => setField("phone", v)} />
        <Field label="Location" value={resume.location} onChange={(v) => setField("location", v)} />
        <Field label="LinkedIn" value={resume.linkedin_url} onChange={(v) => setField("linkedin_url", v)} />
        <Field label="Portfolio" value={resume.portfolio_url} onChange={(v) => setField("portfolio_url", v)} />
      </div>

      <div style={{ marginTop: 16 }}>
        <label style={label}>Professional Summary</label>
        <textarea
          value={resume.professional_summary}
          onChange={(e) => setField("professional_summary", e.target.value)}
          rows={3}
          style={textareaStyle}
        />
      </div>

      <div style={{ marginTop: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <label style={label}>Education</label>
          <Button
            variant="ghost"
            type="button"
            onClick={() =>
              setField("education", [
                ...resume.education,
                { school: "", degree: "", field_of_study: "", start_date: "", end_date: "", honors: "" },
              ])
            }
            style={{ padding: "4px 0", fontSize: "var(--text-sm)" }}
          >
            + Add Education
          </Button>
        </div>
        {resume.education.length === 0 && <EmptyRow />}
        {resume.education.map((entry, i) => (
          <EntryCard key={i} onRemove={() => setField("education", resume.education.filter((_, j) => j !== i))}>
            <Field label="School" value={entry.school} onChange={(v) => updateEducation(i, { ...entry, school: v })} />
            <Field label="Degree" value={entry.degree} onChange={(v) => updateEducation(i, { ...entry, degree: v })} />
            <Field
              label="Field of Study"
              value={entry.field_of_study}
              onChange={(v) => updateEducation(i, { ...entry, field_of_study: v })}
            />
            <Field label="Honors" value={entry.honors} onChange={(v) => updateEducation(i, { ...entry, honors: v })} />
            <Field
              label="Start Date"
              value={entry.start_date}
              onChange={(v) => updateEducation(i, { ...entry, start_date: v })}
            />
            <Field label="End Date" value={entry.end_date} onChange={(v) => updateEducation(i, { ...entry, end_date: v })} />
          </EntryCard>
        ))}
      </div>

      <div style={{ marginTop: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <label style={label}>Work Experience</label>
          <Button
            variant="ghost"
            type="button"
            onClick={() =>
              setField("experience", [
                ...resume.experience,
                { company: "", title: "", start_date: "", end_date: "", description: "" },
              ])
            }
            style={{ padding: "4px 0", fontSize: "var(--text-sm)" }}
          >
            + Add Experience
          </Button>
        </div>
        {resume.experience.length === 0 && <EmptyRow />}
        {resume.experience.map((entry, i) => (
          <EntryCard key={i} onRemove={() => setField("experience", resume.experience.filter((_, j) => j !== i))}>
            <Field label="Company" value={entry.company} onChange={(v) => updateExperience(i, { ...entry, company: v })} />
            <Field label="Title" value={entry.title} onChange={(v) => updateExperience(i, { ...entry, title: v })} />
            <Field
              label="Start Date"
              value={entry.start_date}
              onChange={(v) => updateExperience(i, { ...entry, start_date: v })}
            />
            <Field label="End Date" value={entry.end_date} onChange={(v) => updateExperience(i, { ...entry, end_date: v })} />
            <div style={{ gridColumn: "1 / -1" }}>
              <label style={label}>Description</label>
              <textarea
                value={entry.description}
                onChange={(e) => updateExperience(i, { ...entry, description: e.target.value })}
                rows={2}
                style={textareaStyle}
              />
            </div>
          </EntryCard>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginTop: 20 }}>
        <div>
          <label style={label}>Skills</label>
          <p style={{ ...subtext, marginTop: 0, marginBottom: 6 }}>Comma-separated.</p>
          <input
            type="text"
            value={resume.skillsText}
            onChange={(e) => setField("skillsText", e.target.value)}
            style={inputStyle}
          />
        </div>
        <div>
          <label style={label}>Certifications</label>
          <p style={{ ...subtext, marginTop: 0, marginBottom: 6 }}>Comma-separated.</p>
          <input
            type="text"
            value={resume.certificationsText}
            onChange={(e) => setField("certificationsText", e.target.value)}
            style={inputStyle}
          />
        </div>
      </div>

      <div style={{ marginTop: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <label style={label}>Other Sections</label>
          <Button
            variant="ghost"
            type="button"
            onClick={() => setField("additional_sections", [...resume.additional_sections, { title: "", content: "" }])}
            style={{ padding: "4px 0", fontSize: "var(--text-sm)" }}
          >
            + Add Section
          </Button>
        </div>
        <p style={{ ...subtext, marginTop: 0, marginBottom: 0 }}>
          Anything else on your resume, such as projects, awards, organizations or seminars.
        </p>
        {resume.additional_sections.length === 0 && <EmptyRow />}
        {resume.additional_sections.map((section, i) => (
          <EntryCard
            key={i}
            onRemove={() =>
              setField(
                "additional_sections",
                resume.additional_sections.filter((_, j) => j !== i)
              )
            }
          >
            <div style={{ gridColumn: "1 / -1" }}>
              <Field label="Section Title" value={section.title} onChange={(v) => updateSection(i, { ...section, title: v })} />
            </div>
            <div style={{ gridColumn: "1 / -1" }}>
              <label style={label}>Details</label>
              <textarea
                value={section.content}
                onChange={(e) => updateSection(i, { ...section, content: e.target.value })}
                rows={3}
                placeholder="One item per line."
                style={textareaStyle}
              />
            </div>
          </EntryCard>
        ))}
      </div>

      <div style={{ marginTop: 20 }}>
        <label style={label}>Letter of Intent (optional)</label>
        <textarea value={letterOfIntent} onChange={(e) => setLetterOfIntent(e.target.value)} rows={4} style={textareaStyle} />
      </div>

      {error && <p style={{ color: "crimson", fontSize: "var(--text-sm)", marginTop: 16 }}>{error}</p>}

      {submitting && (
        <ReadingProgress
          title="Submitting your application"
          steps={SUBMIT_STEPS}
          expectedMs={SUBMIT_EXPECTED_MS}
          done={submitted}
          fileName={file.name}
        />
      )}

      <div style={{ display: "flex", gap: 8, marginTop: 24 }}>
        <Button variant="secondary" onClick={onBack} disabled={submitting}>
          Back to Upload
        </Button>
        {/* Asks first: what is sent
            here is what HR reads and what the match is scored on. */}
        <Button variant="primary" disabled={submitting || !canSubmit} onClick={() => setConfirmingSubmit(true)}>
          {submitting ? "Submitting..." : "Submit Documents"}
        </Button>
      </div>

      <ConfirmDialog
        open={confirmingSubmit}
        title="Submit your application?"
        description="Have you double-checked your details? You can't edit them after submitting."
        confirmLabel="Submit"
        cancelLabel="Keep editing"
        width={440}
        onConfirm={() => {
          setConfirmingSubmit(false);
          void handleSubmit();
        }}
        onCancel={() => setConfirmingSubmit(false)}
      />
    </div>
  );
}
