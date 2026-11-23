import { useState } from "react";
import { ChevronLeftIcon, ChevronRightIcon } from "./icons";
import { todayInPhilippines } from "../lib/scheduleTime";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const WEEKDAY_INITIALS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

function iso(year: number, month: number, day: number): string {
  return `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/** A month at a time, as a grid of days to press. Native date inputs can't
 *  grey out arbitrary days, and exam booking needs exactly that — only the
 *  days with a free seat can be picked. Used for one day (the applicant's
 *  booking) and for several (HR adding sessions): the caller decides what
 *  pressing a day does with `onPick`.
 *
 *  Days are plain YYYY-MM-DD strings throughout, so nothing here is ever
 *  shifted by the viewer's time zone. */
export function CalendarPicker({
  selected,
  onPick,
  isEnabled,
  label,
}: {
  selected: string[];
  onPick: (day: string) => void;
  isEnabled: (day: string) => boolean;
  /** Names the grid for screen readers. */
  label: string;
}) {
  // Opens on the first chosen day, else the first day that can be
  // picked within the next year, else this month.
  const [view, setView] = useState(() => {
    const start = selected[0] ?? firstEnabled(isEnabled) ?? todayInPhilippines();
    const [year, month] = start.split("-").map(Number);
    return { year, month: month - 1 };
  });

  const daysInMonth = new Date(Date.UTC(view.year, view.month + 1, 0)).getUTCDate();
  const leadingBlanks = new Date(Date.UTC(view.year, view.month, 1)).getUTCDay();
  const today = todayInPhilippines();

  function shift(by: number) {
    setView(({ year, month }) => {
      const next = month + by;
      return { year: year + Math.floor(next / 12), month: ((next % 12) + 12) % 12 };
    });
  }

  return (
    <div className="ark-cal">
      <div className="ark-cal__head">
        <button type="button" className="ark-icon-btn" aria-label="Previous month" onClick={() => shift(-1)}>
          <ChevronLeftIcon width={16} height={16} />
        </button>
        <span className="ark-cal__month" aria-live="polite">
          {MONTH_NAMES[view.month]} {view.year}
        </span>
        <button type="button" className="ark-icon-btn" aria-label="Next month" onClick={() => shift(1)}>
          <ChevronRightIcon width={16} height={16} />
        </button>
      </div>
      <div className="ark-cal__grid" role="group" aria-label={label}>
        {WEEKDAY_INITIALS.map((initial) => (
          <span key={initial} className="ark-cal__weekday" aria-hidden="true">
            {initial}
          </span>
        ))}
        {Array.from({ length: leadingBlanks }, (_, i) => (
          <span key={`blank-${i}`} aria-hidden="true" />
        ))}
        {Array.from({ length: daysInMonth }, (_, i) => {
          const day = iso(view.year, view.month, i + 1);
          const enabled = isEnabled(day);
          const isSelected = selected.includes(day);
          return (
            <button
              key={day}
              type="button"
              className="ark-cal__day"
              aria-pressed={isSelected}
              aria-label={day}
              data-today={day === today || undefined}
              disabled={!enabled}
              onClick={() => onPick(day)}
            >
              {i + 1}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function firstEnabled(isEnabled: (day: string) => boolean): string | null {
  const [year, month, day] = todayInPhilippines().split("-").map(Number);
  for (let offset = 0; offset < 366; offset += 1) {
    const date = new Date(Date.UTC(year, month - 1, day + offset));
    const candidate = iso(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
    if (isEnabled(candidate)) return candidate;
  }
  return null;
}
