import { describe, expect, it } from "vitest";
import { formatClock, formatDay, formatWindow, minTimeFor, timeNowInPhilippines, todayInPhilippines } from "./scheduleTime";

// 15 Oct 2026, 06:00 UTC = 2:00 PM in the Philippines
const NOW = new Date(Date.UTC(2026, 9, 15, 6, 0));

describe("scheduleTime", () => {
  it("reads today and now in Philippine time", () => {
    expect(todayInPhilippines(NOW)).toBe("2026-10-15");
    expect(timeNowInPhilippines(NOW)).toBe("14:00");
  });

  it("rolls the date over at Philippine midnight, not UTC midnight", () => {
    // 16:30 UTC on the 15th is 00:30 on the 16th in Manila
    expect(todayInPhilippines(new Date(Date.UTC(2026, 9, 15, 16, 30)))).toBe("2026-10-16");
  });

  it("only limits the time when the date is today", () => {
    expect(minTimeFor("2026-10-15", NOW)).toBe("14:00");
    expect(minTimeFor("2026-10-16", NOW)).toBeUndefined();
  });

  it("writes days and times the way people read them", () => {
    expect(formatDay("2030-03-01")).toBe("Fri, 1 Mar 2030");
    expect(formatClock("09:00")).toBe("9:00 AM");
    expect(formatClock("12:15")).toBe("12:15 PM");
    expect(formatClock("00:05")).toBe("12:05 AM");
    expect(formatWindow("13:00", "16:30")).toBe("1:00 PM – 4:30 PM");
    expect(formatWindow("13:00", null)).toBe("1:00 PM");
  });
});
