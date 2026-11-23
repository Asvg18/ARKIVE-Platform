import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { Button } from "../../../../shared/ui/Button";
import { Modal } from "../../../../shared/ui/Modal";
import { MinusIcon, PlusIcon } from "../../../../shared/ui/icons";

/** The frame the photo is framed in, on screen. */
const STAGE = 300;
/** The saved photo's side. The photo viewer lets people zoom in, and
 *  this stays sharp at the viewer's size while still only ~100–200 KB as
 *  a JPEG, well under the 2 MB cap. */
export const PHOTO_SIZE = 640;
const MAX_ZOOM = 4;

interface Framing {
  zoom: number;
  /** The image's top-left corner, relative to the stage's. */
  x: number;
  y: number;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** Choosing which part of a photo to use, before it is uploaded.
 *
 *  A square cut from the centre would take the top off a head in a
 *  portrait taken with room above it, so the picked photo opens here:
 *  drag it to move it, zoom with the slider or the mouse wheel (arrow
 *  keys and +/− from the keyboard), with a live preview of how it will
 *  look at the sizes it is shown at.
 *
 *  The crop is drawn and re-encoded in the browser — which is
 *  also what strips a phone photo's hidden location data — so the server
 *  still only ever receives a plain square JPEG. */
export function PhotoCropDialog({
  file,
  saving,
  error,
  onCancel,
  onSave,
}: {
  file: File | null;
  saving: boolean;
  error: string | null;
  onCancel: () => void;
  onSave: (photo: Blob) => void;
}) {
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [unreadable, setUnreadable] = useState(false);
  const [framing, setFraming] = useState<Framing>({ zoom: 1, x: 0, y: 0 });
  const stageRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; fx: number; fy: number } | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  // Drawing and encoding the crop takes a moment before the upload (and
  // `saving`) begins; the button says so from the click.
  const [encoding, setEncoding] = useState(false);
  const busy = saving || encoding;

  // Load the picked file into an <img> — which is what the stage shows
  // and what the canvas draws from, so the two can never disagree about
  // which way up a phone photo is.
  useEffect(() => {
    setImage(null);
    setUnreadable(false);
    setEncoding(false);
    if (!file) return;
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      setImage(img);
      setFraming(fitted(img, 1));
    };
    img.onerror = () => setUnreadable(true);
    img.src = url;
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  /** At zoom 1 the shorter side exactly fills the stage (as the old
   *  centre crop did), and the picture starts centred. */
  function baseScale(img: HTMLImageElement): number {
    return STAGE / Math.min(img.naturalWidth, img.naturalHeight);
  }

  function fitted(img: HTMLImageElement, zoom: number): Framing {
    const scale = baseScale(img) * zoom;
    return {
      zoom,
      x: (STAGE - img.naturalWidth * scale) / 2,
      y: (STAGE - img.naturalHeight * scale) / 2,
    };
  }

  /** The picture always covers the whole frame — no empty corner can
   *  end up in the saved photo. */
  function constrain(next: Framing, img: HTMLImageElement): Framing {
    const scale = baseScale(img) * next.zoom;
    const w = img.naturalWidth * scale;
    const h = img.naturalHeight * scale;
    return { zoom: next.zoom, x: clamp(next.x, STAGE - w, 0), y: clamp(next.y, STAGE - h, 0) };
  }

  /** Zooms about the middle of the frame, so what you are looking at
   *  stays where it is. */
  function zoomTo(next: (current: number) => number) {
    if (!image) return;
    setFraming((f) => {
      const zoom = clamp(next(f.zoom), 1, MAX_ZOOM);
      const ratio = zoom / f.zoom;
      const cx = STAGE / 2;
      return constrain({ zoom, x: cx - (cx - f.x) * ratio, y: cx - (cx - f.y) * ratio }, image);
    });
  }

  function moveBy(dx: number, dy: number) {
    if (!image) return;
    setFraming((f) => constrain({ ...f, x: f.x + dx, y: f.y + dy }, image));
  }

  // Not React's onWheel, which is passive: the wheel must not also
  // scroll the dialog behind the photo.
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage || !image) return;
    function onWheel(event: WheelEvent) {
      event.preventDefault();
      zoomTo((z) => z * (event.deltaY < 0 ? 1.08 : 1 / 1.08));
    }
    stage.addEventListener("wheel", onWheel, { passive: false });
    return () => stage.removeEventListener("wheel", onWheel);
  });

  function onPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { x: event.clientX, y: event.clientY, fx: framing.x, fy: framing.y };
  }

  function onPointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    const start = drag.current;
    if (!start || !image) return;
    setFraming((f) =>
      constrain({ ...f, x: start.fx + event.clientX - start.x, y: start.fy + event.clientY - start.y }, image)
    );
  }

  function onKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    const step = event.shiftKey ? 30 : 8;
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [step, 0],
      ArrowRight: [-step, 0],
      ArrowUp: [0, step],
      ArrowDown: [0, -step],
    };
    if (moves[event.key]) {
      event.preventDefault();
      moveBy(...moves[event.key]);
    } else if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      zoomTo((z) => z + 0.1);
    } else if (event.key === "-") {
      event.preventDefault();
      zoomTo((z) => z - 0.1);
    }
  }

  function save() {
    if (!image) return;
    const scale = baseScale(image) * framing.zoom;
    const canvas = document.createElement("canvas");
    canvas.width = PHOTO_SIZE;
    canvas.height = PHOTO_SIZE;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    // A transparent PNG would otherwise turn black as a JPEG.
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, PHOTO_SIZE, PHOTO_SIZE);
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(image, -framing.x / scale, -framing.y / scale, STAGE / scale, STAGE / scale, 0, 0, PHOTO_SIZE, PHOTO_SIZE);
    setEncoding(true);
    canvas.toBlob(
      (blob) => {
        setEncoding(false);
        if (blob) onSave(blob);
      },
      "image/jpeg",
      0.9
    );
  }

  const scale = image ? baseScale(image) * framing.zoom : 1;
  const imageStyle = image
    ? {
        width: image.naturalWidth * scale,
        height: image.naturalHeight * scale,
        transform: `translate(${framing.x}px, ${framing.y}px)`,
      }
    : undefined;

  return (
    <Modal
      open={!!file}
      title="Adjust your photo"
      sub="Drag to move it, and zoom to frame your face. The circle is what people see."
      width={600}
      busy={busy}
      onClose={onCancel}
      footer={
        <>
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" onClick={save} disabled={!image || busy}>
            {busy ? "Saving…" : "Save photo"}
          </Button>
        </>
      }
    >
      {unreadable ? (
        <p className="ark-crop__error">That image couldn't be read. Please choose a JPG, PNG or WebP photo.</p>
      ) : (
        <div className="ark-crop">
          <div
            ref={stageRef}
            className="ark-crop__stage"
            style={{ width: STAGE, height: STAGE }}
            tabIndex={0}
            role="group"
            aria-label="Photo position. Drag, or use the arrow keys to move it and + or − to zoom."
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={() => (drag.current = null)}
            onPointerCancel={() => (drag.current = null)}
            onKeyDown={onKeyDown}
          >
            {image && previewUrl && <img src={previewUrl} alt="" draggable={false} style={imageStyle} />}
            <span className="ark-crop__mask" aria-hidden="true" />
          </div>

          <div className="ark-crop__side">
            <div className="ark-crop__zoom">
              <label htmlFor="crop-zoom" className="ark-field__label">
                Zoom
              </label>
              <div className="ark-crop__slider">
                <button type="button" className="ark-crop__step" onClick={() => zoomTo((z) => z - 0.25)} aria-label="Zoom out">
                  <MinusIcon width={14} height={14} />
                </button>
                <input
                  id="crop-zoom"
                  type="range"
                  min={1}
                  max={MAX_ZOOM}
                  step={0.01}
                  value={framing.zoom}
                  onChange={(e) => {
                    const value = Number(e.target.value);
                    zoomTo(() => value);
                  }}
                  disabled={!image}
                />
                <button type="button" className="ark-crop__step" onClick={() => zoomTo((z) => z + 0.25)} aria-label="Zoom in">
                  <PlusIcon width={14} height={14} />
                </button>
              </div>
              <button type="button" className="ark-go" onClick={() => image && setFraming(fitted(image, 1))} disabled={!image}>
                Reset
              </button>
            </div>

            {/* The same crop at the sizes ARKIVE shows it: the top bar and
                lists (36), and a profile card (72). */}
            <div className="ark-crop__previews">
              <span className="ark-field__label">Preview</span>
              <div className="ark-crop__preview-row">
                {[72, 36].map((size) => (
                  <span key={size} className="ark-crop__preview" style={{ width: size, height: size }}>
                    {image && previewUrl && (
                      <img
                        src={previewUrl}
                        alt=""
                        style={{
                          width: (image.naturalWidth * scale * size) / STAGE,
                          height: (image.naturalHeight * scale * size) / STAGE,
                          transform: `translate(${(framing.x * size) / STAGE}px, ${(framing.y * size) / STAGE}px)`,
                        }}
                      />
                    )}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
      {error && <p className="ark-crop__error" role="alert">{error}</p>}
    </Modal>
  );
}
