import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** A dialog with room for a small flow inside it — a heading, a body that
 *  scrolls on its own, and a footer of actions, laid out like the Create
 *  Job Opening panel so a step inside a dialog reads the same as a step on
 *  a page. ConfirmDialog stays the choice for a yes/no question; this is
 *  for a task.
 *
 *  Escape and a click on the backdrop close it, unless `busy` — a request
 *  in flight shouldn't be abandoned by a stray click outside. */
export function Modal({
  open,
  title,
  sub,
  aside,
  footer,
  busy = false,
  width = 680,
  onClose,
  children,
}: {
  open: boolean;
  title: ReactNode;
  sub?: ReactNode;
  aside?: ReactNode;
  footer?: ReactNode;
  busy?: boolean;
  width?: number;
  onClose: () => void;
  children: ReactNode;
}) {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, busy, onClose]);

  // Focus moves into the dialog on open, so the keyboard and screen
  // readers start inside it rather than on the page behind.
  useEffect(() => {
    if (open) panelRef.current?.focus();
  }, [open]);

  if (!open) return null;

  return createPortal(
    <div className="ark-modal" role="presentation" onMouseDown={() => !busy && onClose()}>
      <div
        ref={panelRef}
        className="ark-modal__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        style={{ width }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="ark-wizard__head">
          <div className="ark-wizard__heading">
            <h2 id={titleId} className="ark-wizard__title">
              {title}
            </h2>
            {sub && <p className="ark-wizard__sub">{sub}</p>}
          </div>
          {aside}
        </div>
        <div className="ark-modal__body">{children}</div>
        {footer && <div className="ark-wizard__foot">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}
