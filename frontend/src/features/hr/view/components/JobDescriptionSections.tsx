import { useId } from "react";
import type { JobDescriptionSection } from "../../../../shared/api/pipeline";
import { Button } from "../../../../shared/ui/Button";
import { PlusIcon, XIcon } from "../../../../shared/ui/icons";
import { cleanSections } from "../../model/jobSections";

/** The job description's other sections as editable boxes — everything
 *  the document says that Role description, Qualifications and
 *  Requirements have no place for. Used by Create Job Opening's review
 *  step, the job opening page's Edit, and the Replace dialog. */
export function JobSectionsEditor({
  sections,
  changed = false,
  onChange,
}: {
  sections: JobDescriptionSection[];
  /** Marks the group when it differs from the text in force. */
  changed?: boolean;
  onChange: (sections: JobDescriptionSection[]) => void;
}) {
  const labelId = useId();
  const hintId = useId();

  function update(index: number, section: JobDescriptionSection) {
    onChange(sections.map((s, i) => (i === index ? section : s)));
  }

  return (
    <div className="ark-field" role="group" aria-labelledby={labelId} aria-describedby={hintId}>
      <div className="ark-field__label-row">
        <span id={labelId} className="ark-field__label">
          Other sections
          <span className="ark-field__req">Optional</span>
        </span>
        {changed && <span className="ark-field__flag ark-field__flag--changed">Changed</span>}
      </div>
      <p id={hintId} className="ark-field__hint">
        Anything else in the job description, such as duties, salary, benefits or documents to submit. Applicants see
        these. The match score doesn't use them.
      </p>

      {sections.map((section, i) => (
        <SectionBox
          key={i}
          index={i}
          section={section}
          onChange={(next) => update(i, next)}
          onRemove={() => onChange(sections.filter((_, j) => j !== i))}
        />
      ))}

      <div>
        <Button
          variant="ghost"
          size="sm"
          type="button"
          onClick={() => onChange([...sections, { title: "", content: "" }])}
        >
          <PlusIcon width={14} height={14} aria-hidden="true" />
          Add section
        </Button>
      </div>
    </div>
  );
}

function SectionBox({
  index,
  section,
  onChange,
  onRemove,
}: {
  index: number;
  section: JobDescriptionSection;
  onChange: (section: JobDescriptionSection) => void;
  onRemove: () => void;
}) {
  const titleId = useId();
  const contentId = useId();
  const name = section.title.trim() || `section ${index + 1}`;
  return (
    <div className="ark-jd-section-edit">
      <div className="ark-jd-section-edit__head">
        <label className="ark-visually-hidden" htmlFor={titleId}>
          Section title
        </label>
        <input
          id={titleId}
          className="ark-input"
          value={section.title}
          onChange={(e) => onChange({ ...section, title: e.target.value })}
          placeholder="Section title, e.g. Salary"
        />
        <button type="button" className="ark-file__remove" aria-label={`Remove ${name}`} onClick={onRemove}>
          <XIcon width={15} height={15} />
        </button>
      </div>
      <label className="ark-visually-hidden" htmlFor={contentId}>
        Details for {name}
      </label>
      <textarea
        id={contentId}
        className="ark-input"
        rows={3}
        value={section.content}
        onChange={(e) => onChange({ ...section, content: e.target.value })}
        placeholder="One item per line"
      />
    </div>
  );
}

/** The other sections, read-only, inside an `.ark-jd-text` stack. Says
 *  "None" rather than vanishing, so HR can see the job has none and
 *  knows Edit is where to add them. */
export function JobSectionsView({
  sections,
  loading = false,
  emptyText = "None",
}: {
  sections: JobDescriptionSection[] | undefined;
  loading?: boolean;
  emptyText?: string;
}) {
  const shown = cleanSections(sections ?? []);
  return (
    <div className="ark-jd-text__section">
      <p className="ark-jd-text__label">Other sections</p>
      {loading ? (
        <span className="ark-skeleton" style={{ display: "block", height: 12, width: "60%" }} />
      ) : shown.length === 0 ? (
        <p className="ark-jd-text__body" data-empty="">
          {emptyText}
        </p>
      ) : (
        <div className="ark-jd-sections">
          {shown.map((s, i) => (
            <div key={i}>
              {s.title && <p className="ark-jd-sections__title">{s.title}</p>}
              {s.content && <p className="ark-jd-text__body">{s.content}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
