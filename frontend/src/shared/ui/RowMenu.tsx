import { Fragment, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { ChevronDownIcon, MoreIcon } from "./icons";

export interface RowMenuItem {
  label: string;
  /** Navigation target. Omit together with `disabled` to render a dead item. */
  to?: string;
  /**
   * In-place action, for a menu entry that does something to this row
   * rather than navigating away from it (deleting the thing the row
   * describes). Mutually exclusive with `to`; `to` wins if both are set.
   */
  onClick?: () => void;
  icon?: ReactNode;
  /**
   * A second line under the label saying what the action will do. For a
   * menu someone may be opening for the first time, where "Close" and
   * "Delete" sit a few pixels apart and mean very different things — the
   * consequence is read at the moment of choosing, not in a dialog after.
   */
  description?: string;
  /** When set, the item renders greyed and unclickable, with `hint` explaining why. */
  disabled?: boolean;
  hint?: string;
  /**
   * "danger" colours the label red, for an action that destroys
   * something. A destructive entry sitting in the same quiet grey as
   * "Edit Workflow" is the one thing in a menu that should never look
   * routine — pair it with an icon so it reads as dangerous before the
   * label is read at all.
   */
  tone?: "default" | "danger";
  /** Draws a hairline above this item, fencing it off from the ones
   *  before it — how a destructive action is kept out of reach of a
   *  slip aimed at its neighbour. */
  separated?: boolean;
}

const GAP = 8;

/** Row actions behind one trigger.
 *
 * Rows here put their *primary* action on the row itself (click to open
 * the thing it describes). Stacking every remaining action as its own
 * always-visible link made these tables read as noisy -- a row with
 * three equally-weighted links has no primary action at all. Secondary
 * actions live here instead, one quiet trigger per row.
 *
 * The trigger is a bare ⋮ by default. Pass `triggerLabel` where the menu
 * is the row's *only* action — there is no row click to fall back on,
 * so the control has to say what it is to someone seeing it for the
 * first time.
 *
 * The panel is portalled to <body> with fixed coordinates. These tables
 * sit in an `overflow-x: auto` wrapper, and CSS makes that clip vertically
 * too, so an in-flow panel on the bottom rows was cut off by the card.
 * It opens upward when there is no room below.
 *
 * Open/close behavior mirrors ProfileMenu deliberately, so both
 * dropdowns dismiss identically. Clicks and keys are stopped from
 * bubbling because this lives inside a click-to-navigate row — React
 * carries portal events up the component tree, not the DOM one, so the
 * row still sees them unless they are stopped here. */
export function RowMenu({ label, items, triggerLabel }: { label: string; items: RowMenuItem[]; triggerLabel?: string }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  // Keyboard opens move focus into the menu; mouse opens leave it on
  // the trigger, so the first item doesn't light up as if hovered.
  const focusFirstOnOpen = useRef(false);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      const target = event.target as Node;
      if (containerRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      setOpen(false);
    }
    // Fallback for when focus is not inside the menu at all (Safari does
    // not focus a clicked button); in-menu keys are handled in onKeyDown.
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  // Placed imperatively before paint rather than through state, so the
  // panel never renders a frame at the wrong spot and is already visible
  // (hence focusable) by the time focus moves into it.
  useLayoutEffect(() => {
    if (!open) return;
    const trigger = triggerRef.current;
    const menu = menuRef.current;
    if (!trigger || !menu) return;

    function place() {
      if (!trigger || !menu) return;
      const r = trigger.getBoundingClientRect();
      const h = menu.offsetHeight;
      const up = r.bottom + GAP + h > window.innerHeight - GAP && r.top - GAP - h >= GAP;
      menu.style.top = `${up ? r.top - GAP - h : r.bottom + GAP}px`;
      menu.style.right = `${document.documentElement.clientWidth - r.right}px`;
      menu.classList.toggle("ark-menu--up", up);
    }

    place();
    if (focusFirstOnOpen.current) menuItems(menu).find(isEnabled)?.focus({ preventScroll: true });
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open]);

  function close(returnFocus: boolean) {
    setOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  }

  function onKeyDown(event: ReactKeyboardEvent) {
    event.stopPropagation();
    const menu = menuRef.current;
    const onTrigger = event.target === triggerRef.current;

    if (event.key === "Escape" && open) {
      event.preventDefault();
      close(true);
      return;
    }
    if (event.key === "Tab" && open) {
      // Back to the trigger and let Tab carry on from there, so focus
      // lands on the next thing in the row rather than at the end of
      // <body>, where the panel actually lives.
      if (!onTrigger) triggerRef.current?.focus();
      setOpen(false);
      return;
    }
    if (onTrigger) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (!open) {
          focusFirstOnOpen.current = true;
          setOpen(true);
        } else if (menu) {
          const all = menuItems(menu);
          (event.key === "ArrowDown" ? all.find(isEnabled) : all[all.length - 1])?.focus();
        }
      }
      return;
    }
    if (!menu) return;

    // Arrow keys walk every item, disabled ones included, so a keyboard
    // or screen-reader user still hears why "Delete" can't be used.
    const all = menuItems(menu);
    const at = all.indexOf(document.activeElement as HTMLElement);
    let next: HTMLElement | undefined;
    if (event.key === "ArrowDown") next = all[(at + 1) % all.length];
    else if (event.key === "ArrowUp") next = all[(at - 1 + all.length) % all.length];
    else if (event.key === "Home") next = all[0];
    else if (event.key === "End") next = all[all.length - 1];
    if (next) {
      event.preventDefault();
      next.focus();
    }
  }

  return (
    <div
      ref={containerRef}
      style={{ position: "relative", display: "inline-flex" }}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={onKeyDown}
    >
      <button
        ref={triggerRef}
        onClick={(e) => {
          e.stopPropagation();
          // detail is 0 for a click synthesised from Enter or Space
          focusFirstOnOpen.current = e.detail === 0;
          setOpen((prev) => !prev);
        }}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        type="button"
        className={triggerLabel ? "ark-btn ark-btn--outline ark-btn--sm ark-menu-trigger" : "ark-kebab"}
      >
        {triggerLabel ? (
          <>
            {triggerLabel}
            <ChevronDownIcon width={15} height={15} className="ark-menu-trigger__caret" aria-hidden="true" />
          </>
        ) : (
          <MoreIcon width={17} height={17} style={{ flexShrink: 0 }} />
        )}
      </button>

      {open &&
        createPortal(
          <div
            ref={menuRef}
            role="menu"
            aria-label={label}
            className="ark-menu ark-menu--floating"
            style={{ minWidth: items.some((i) => i.description) ? 264 : 210 }}
          >
            {items.map((item) => {
              const sub = item.disabled ? item.hint : item.description;
              const content = (
                <>
                  <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    {item.icon}
                    {item.label}
                  </span>
                  {sub && (
                    <span className="ark-menu__sub" style={{ paddingLeft: item.icon ? 23 : 0 }}>
                      {sub}
                    </span>
                  )}
                </>
              );
              const className = ["ark-menu__item", item.tone === "danger" ? "ark-menu__item--danger" : ""]
                .filter(Boolean)
                .join(" ");

              let entry: ReactNode;
              if (item.disabled || (!item.to && !item.onClick)) {
                entry = (
                  <div role="menuitem" aria-disabled="true" tabIndex={-1} className="ark-menu__item" style={itemStyle}>
                    {content}
                  </div>
                );
              } else if (item.to) {
                entry = (
                  <Link
                    to={item.to}
                    role="menuitem"
                    tabIndex={-1}
                    className={className}
                    onClick={() => setOpen(false)}
                    style={itemStyle}
                  >
                    {content}
                  </Link>
                );
              } else {
                entry = (
                  <button
                    type="button"
                    role="menuitem"
                    tabIndex={-1}
                    className={className}
                    onClick={(e) => {
                      // the row behind this menu navigates on click, and the
                      // container's stopPropagation only covers the pointer
                      // events it sees -- belt and braces for the one item
                      // that must never navigate by accident
                      e.stopPropagation();
                      setOpen(false);
                      item.onClick?.();
                    }}
                    style={itemStyle}
                  >
                    {content}
                  </button>
                );
              }

              return (
                <Fragment key={item.label}>
                  {item.separated && <div role="separator" className="ark-menu__sep" />}
                  {entry}
                </Fragment>
              );
            })}
          </div>,
          document.body,
        )}
    </div>
  );
}

function menuItems(menu: HTMLElement): HTMLElement[] {
  return Array.from(menu.querySelectorAll<HTMLElement>('[role="menuitem"]'));
}

function isEnabled(el: HTMLElement): boolean {
  return el.getAttribute("aria-disabled") !== "true";
}

const itemStyle: React.CSSProperties = {
  flexDirection: "column",
  alignItems: "stretch",
  gap: 3,
  padding: "9px 10px",
  fontWeight: 600,
  boxSizing: "border-box",
};
