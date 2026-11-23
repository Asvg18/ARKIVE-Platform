import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { BASE_URL } from "../api/client";
import { MinusIcon, PlusIcon, XIcon } from "./icons";

const MIN_ZOOM = 1;
const MAX_ZOOM = 3;
const STEP = 0.25;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** A profile photo, full size, on a dimmed page — opened by clicking the
 *  photo where it is shown large (Account Settings).
 *
 *  Zoom with the buttons, the mouse wheel or a double-click; once zoomed
 *  in, drag to look around. The picture never leaves its frame, so
 *  there is no way to lose it off-screen. Escape or the backdrop closes
 *  it, and focus goes back to whatever opened it.
 *
 *  `src` is the avatar_url the API hands out (relative to the API), as
 *  Avatar takes. `actions` sit under the photo — Account Settings puts
 *  "Change photo" there. */
export function PhotoViewer({
  open,
  src,
  name,
  caption,
  actions,
  onClose,
}: {
  open: boolean;
  src: string | null;
  name: string;
  caption?: ReactNode;
  actions?: ReactNode;
  onClose: () => void;
}) {
  // Zoom and pan in one state, so each change builds on the latest of
  // both — two quick clicks on + must zoom twice, not once.
  const [view, setView] = useState({ zoom: 1, x: 0, y: 0 });
  const { zoom } = view;
  const frameRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const drag = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);

  // Each opening starts from the whole photo, and hands focus back to
  // whatever opened it on the way out.
  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement as HTMLElement | null;
    setView({ zoom: 1, x: 0, y: 0 });
    closeRef.current?.focus();
    return () => opener?.focus?.();
  }, [open]);

  /** Keeps the picture covering its frame: at a given zoom it can only
   *  move as far as the part hanging outside the frame. */
  function clampPan(x: number, y: number, atZoom: number) {
    const side = frameRef.current?.clientWidth ?? 0;
    const limit = (side * (atZoom - 1)) / 2;
    return { x: clamp(x, -limit, limit), y: clamp(y, -limit, limit) };
  }

  /** Zooms about the middle of the frame, from whatever the zoom is by
   *  the time this runs. */
  function zoomTo(next: (current: number) => number) {
    setView((v) => {
      const z = clamp(Math.round(next(v.zoom) * 100) / 100, MIN_ZOOM, MAX_ZOOM);
      return { zoom: z, ...clampPan((v.x * z) / v.zoom, (v.y * z) / v.zoom, z) };
    });
  }

  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
      else if (event.key === "+" || event.key === "=") zoomTo((z) => z + STEP);
      else if (event.key === "-") zoomTo((z) => z - STEP);
      else if (event.key === "0") zoomTo(() => 1);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  // Not React's onWheel: that listener is passive, and a wheel that
  // zooms has to stop the page behind from scrolling.
  useEffect(() => {
    const frame = frameRef.current;
    if (!open || !frame) return;
    function onWheel(event: WheelEvent) {
      event.preventDefault();
      zoomTo((z) => z * (event.deltaY < 0 ? 1.12 : 1 / 1.12));
    }
    frame.addEventListener("wheel", onWheel, { passive: false });
    return () => frame.removeEventListener("wheel", onWheel);
  });

  function onPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (zoom === 1) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { x: event.clientX, y: event.clientY, panX: view.x, panY: view.y };
  }

  function onPointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    const start = drag.current;
    if (!start) return;
    setView((v) => ({ ...v, ...clampPan(start.panX + event.clientX - start.x, start.panY + event.clientY - start.y, v.zoom) }));
  }

  function onPointerUp() {
    drag.current = null;
  }

  if (!open || !src) return null;

  return createPortal(
    <div className="ark-viewer" role="presentation" onMouseDown={onClose}>
      <div
        className="ark-viewer__dialog"
        role="dialog"
        aria-modal="true"
        aria-label={`${name}'s photo`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="ark-viewer__bar">
          <div className="ark-viewer__title">
            <strong>{name}</strong>
            {caption && <span>{caption}</span>}
          </div>
          <button ref={closeRef} type="button" className="ark-viewer__icon-btn" onClick={onClose} aria-label="Close">
            <XIcon width={18} height={18} />
          </button>
        </div>

        <div
          ref={frameRef}
          className="ark-viewer__frame"
          data-zoomed={zoom > 1 || undefined}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onDoubleClick={() => zoomTo((z) => (z > 1 ? 1 : 2))}
        >
          <img
            src={`${BASE_URL}${src}`}
            alt={`${name}'s profile photo`}
            draggable={false}
            style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${zoom})` }}
          />
        </div>

        <div className="ark-viewer__tools">
          <div className="ark-viewer__zoom" role="group" aria-label="Zoom">
            <button
              type="button"
              className="ark-viewer__icon-btn"
              onClick={() => zoomTo((z) => z - STEP)}
              disabled={zoom <= MIN_ZOOM}
              aria-label="Zoom out"
            >
              <MinusIcon width={16} height={16} />
            </button>
            <button type="button" className="ark-viewer__level" onClick={() => zoomTo(() => 1)} title="Back to the whole photo">
              {Math.round(zoom * 100)}%
            </button>
            <button
              type="button"
              className="ark-viewer__icon-btn"
              onClick={() => zoomTo((z) => z + STEP)}
              disabled={zoom >= MAX_ZOOM}
              aria-label="Zoom in"
            >
              <PlusIcon width={16} height={16} />
            </button>
          </div>
          {actions && <div className="ark-viewer__actions">{actions}</div>}
        </div>
        <p className="ark-viewer__hint">Scroll or double-click to zoom · drag to look around · Esc to close</p>
      </div>
    </div>,
    document.body
  );
}
