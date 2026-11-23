import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { InfoIcon } from "./icons";

/** Space between the trigger and the card — room for the arrow. */
const GAP = 10;
/** Closest the card may sit to the edge of the window. */
const EDGE = 8;
/** For an icon-only trigger: how far in from the card's left edge the
 *  arrow sits, so the card opens to the right of the ⓘ like a flag. */
const ARROW_INSET = 22;
/** How long the card stays in the DOM after closing — long enough for
 *  the exit animation (--dur) to play out. */
const EXIT_MS = 180;

/** An ⓘ that opens a small card of detail.
 *
 * Two shapes. With a `label` it is a short word with the ⓘ beside it, for
 * a table cell whose full story doesn't fit the column: the cell says the
 * one word that matters ("Passed") and the card holds the rest. Without
 * one it is the ⓘ alone — PageHeader uses that to hold what a page is
 * for, so the explanation is one pointer-rest away instead of a
 * paragraph sitting between the title and the work.
 *
 * Opens on hover, keyboard focus, or a click/tap — a click pins it open
 * so it survives the pointer leaving, which is also what makes it work
 * on a touchscreen. The pointer can travel from the trigger into the card
 * without it closing, and Escape dismisses it (WCAG 1.4.13).
 *
 * The card grows out of its arrow and shrinks back into it on close, so
 * it reads as coming from the ⓘ rather than appearing near it. With a
 * label, the card's text starts on the same vertical line as the word
 * that opened it. Like RowMenu it is portalled and placed with fixed
 * coordinates, because the tables it sits in scroll sideways and would
 * otherwise clip it. */
export function InfoTip({
  label,
  ariaLabel,
  children,
  width = 288,
  className,
}: {
  label?: ReactNode;
  /** The trigger's accessible name when there is no label to read. */
  ariaLabel?: string;
  children: ReactNode;
  width?: number;
  /** Extra class on the card, for a variant such as `ark-tip--about`. */
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  // Still in the DOM while the close animation plays.
  const [present, setPresent] = useState(false);
  const pinned = useRef(false);
  const timer = useRef<number | undefined>(undefined);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const labelRef = useRef<HTMLSpanElement>(null);
  const iconRef = useRef<HTMLSpanElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const id = useId();

  // A short delay each way: opening late stops a pointer merely crossing
  // the table from flashing cards, closing late lets it reach the card.
  function later(next: boolean, delay: number) {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(next), delay);
  }
  function show() {
    window.clearTimeout(timer.current);
    setOpen(true);
  }
  function hide() {
    window.clearTimeout(timer.current);
    pinned.current = false;
    setOpen(false);
  }

  useEffect(() => () => window.clearTimeout(timer.current), []);

  useEffect(() => {
    if (open) {
      setPresent(true);
      return;
    }
    const t = window.setTimeout(() => setPresent(false), EXIT_MS);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || tipRef.current?.contains(target)) return;
      hide();
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") hide();
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  useLayoutEffect(() => {
    if (!present) return;
    const trigger = triggerRef.current;
    const icon = iconRef.current;
    const tip = tipRef.current;
    if (!trigger || !icon || !tip) return;

    function place() {
      if (!trigger || !icon || !tip) return;
      const r = trigger.getBoundingClientRect();
      const iconBox = icon.getBoundingClientRect();
      const iconCentre = iconBox.left + iconBox.width / 2;
      const w = tip.offsetWidth;
      const h = tip.offsetHeight;
      let want: number;
      if (labelRef.current) {
        // border + padding: where the card's text actually starts
        const inset = tip.clientLeft + (parseFloat(getComputedStyle(tip).paddingLeft) || 0);
        want = labelRef.current.getBoundingClientRect().left - inset;
      } else {
        want = iconCentre - ARROW_INSET;
      }
      // pulled back in only if the window is too narrow to hold it there
      const left = Math.max(EDGE, Math.min(want, document.documentElement.clientWidth - w - EDGE));
      const up = r.bottom + GAP + h > window.innerHeight - EDGE && r.top - GAP - h >= EDGE;
      tip.style.left = `${left}px`;
      tip.style.top = `${up ? r.top - GAP - h : r.bottom + GAP}px`;
      tip.style.setProperty("--arrow-x", `${iconCentre - left}px`);
      tip.classList.toggle("ark-tip--up", up);
    }

    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [present]);

  const iconOnly = label == null;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className={iconOnly ? "ark-tip-icon" : "ark-tip-trigger"}
        data-open={open || undefined}
        aria-label={iconOnly ? ariaLabel : undefined}
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onMouseEnter={() => later(true, 120)}
        onMouseLeave={() => {
          if (!pinned.current) later(false, 150);
        }}
        onFocus={show}
        onBlur={hide}
        onClick={(e) => {
          e.stopPropagation();
          if (pinned.current) {
            hide();
          } else {
            pinned.current = true;
            show();
          }
        }}
      >
        {!iconOnly && <span ref={labelRef}>{label}</span>}
        <span ref={iconRef} className="ark-tip-trigger__icon" aria-hidden="true">
          <InfoIcon width={iconOnly ? 16 : 14} height={iconOnly ? 16 : 14} />
        </span>
      </button>

      {present &&
        createPortal(
          <div
            ref={tipRef}
            id={id}
            role="tooltip"
            className={["ark-tip", className].filter(Boolean).join(" ")}
            data-state={open ? "open" : "closed"}
            style={{ width }}
            onMouseEnter={() => {
              if (open) window.clearTimeout(timer.current);
            }}
            onMouseLeave={() => {
              if (!pinned.current) later(false, 150);
            }}
            // keeps focus on the trigger, which would otherwise blur and
            // close the card the moment it is clicked
            onMouseDown={(e) => e.preventDefault()}
          >
            {children}
          </div>,
          document.body,
        )}
    </>
  );
}
