/**
 * "Now" in the Philippines, for the `min` on schedule pickers, so a date
 * that has already passed can't be picked. The server refuses a past
 * schedule either way (backend/app/domain/schedule_time.py); this only
 * keeps the picker honest.
 */
const PH_TIME_ZONE = "Asia/Manila";

/** Today as YYYY-MM-DD, the value format of <input type="date">. */
export function todayInPhilippines(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: PH_TIME_ZONE }).format(now);
}

/** The current time as HH:MM, the value format of <input type="time">. */
export function timeNowInPhilippines(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: PH_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(now);
}

/** The `min` for a time picker: only when the chosen date is today. */
export function minTimeFor(date: string, now: Date = new Date()): string | undefined {
  return date === todayInPhilippines(now) ? timeNowInPhilippines(now) : undefined;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** "2030-03-01" → "Fri, 1 Mar 2030". Read as a calendar day, never
 *  shifted by the viewer's time zone. */
export function formatDay(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  const weekday = WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()];
  return `${weekday}, ${day} ${MONTHS[month - 1]} ${year}`;
}

/** "13:30" → "1:30 PM". */
export function formatClock(hhmm: string): string {
  const [hours, minutes] = hhmm.split(":").map(Number);
  const suffix = hours < 12 ? "AM" : "PM";
  const hour12 = hours % 12 === 0 ? 12 : hours % 12;
  return `${hour12}:${String(minutes).padStart(2, "0")} ${suffix}`;
}

/** "9:00 AM – 11:30 AM", or just the start when there is no end. */
export function formatWindow(start: string, end?: string | null): string {
  return end ? `${formatClock(start)} – ${formatClock(end)}` : formatClock(start);
}
