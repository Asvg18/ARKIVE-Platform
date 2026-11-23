import { useState, type ReactNode } from "react";
import { DocumentIcon, UploadIcon, XIcon } from "../../../../shared/ui/icons";

/** The PDF picker for a job description, shared by Create Job Opening and
 *  the Replace dialog: a drop zone while nothing is chosen, then a row
 *  for the chosen file with Replace and Remove. Styled by .ark-drop and
 *  .ark-file in components.css. */

function HiddenPdfInput({ onPick }: { onPick: (file: File | undefined) => void }) {
  return (
    <input
      type="file"
      accept=".pdf,application/pdf"
      className="ark-visually-hidden"
      onChange={(e) => {
        onPick(e.target.files?.[0]);
        // so choosing the same file again still counts as a change
        e.target.value = "";
      }}
    />
  );
}

export function JdDropZone({ onPick }: { onPick: (file: File | undefined) => void }) {
  const [dragOver, setDragOver] = useState(false);
  return (
    <label
      className="ark-drop"
      data-over={dragOver || undefined}
      onDragEnter={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragOver={(e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        onPick(e.dataTransfer.files[0]);
      }}
    >
      <span className="ark-drop__icon">
        <UploadIcon width={20} height={20} />
      </span>
      <span className="ark-drop__title">
        {dragOver ? (
          "Drop to add the PDF"
        ) : (
          <>
            Drag the PDF here, or <span className="ark-drop__link">browse</span>
          </>
        )}
      </span>
      <span className="ark-drop__hint">PDF only · up to 10 MB</span>
      <HiddenPdfInput onPick={onPick} />
    </label>
  );
}

export function JdFileRow({
  file,
  busy,
  meta,
  tone,
  onPick,
  onRemove,
}: {
  file: File;
  /** Being read: hides Replace/Remove and runs the progress bar. */
  busy: boolean;
  meta: ReactNode;
  tone?: "busy" | "done";
  onPick: (file: File | undefined) => void;
  onRemove: () => void;
}) {
  return (
    <div className="ark-file" data-busy={busy || undefined}>
      <span className="ark-file__icon">
        <DocumentIcon width={18} height={18} />
      </span>
      <span className="ark-file__text">
        <span className="ark-file__name">{file.name}</span>
        <span className="ark-file__meta" data-tone={tone}>
          {meta}
        </span>
      </span>
      {!busy && (
        <span className="ark-file__actions">
          <label className="ark-btn ark-btn--ghost ark-btn--sm">
            Replace
            <HiddenPdfInput onPick={onPick} />
          </label>
          <button type="button" className="ark-file__remove" aria-label="Remove file" onClick={onRemove}>
            <XIcon width={15} height={15} />
          </button>
        </span>
      )}
      {busy && <span className="ark-file__progress" aria-hidden="true" />}
    </div>
  );
}
