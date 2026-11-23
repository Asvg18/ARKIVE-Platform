import { describe, expect, it } from "vitest";
import type { ExamSlot } from "../../../shared/api/pipeline";
import { datesBetween, hasStarted, previewSessions, windowProblem } from "./examSessions";

function slot(overrides: Partial<ExamSlot> = {}): ExamSlot {
  return {
    id: 1,
    stage_type: "examination",
    date: "2030-03-01",
    time: "09:00",
    end_time: "11:30",
    location: "Room 204",
    capacity: 20,
    remaining_capacity: 20,
    booked: [],
    ...overrides,
  };
}

describe("datesBetween", () => {
  it("covers every day of the range, both ends included", () => {
    expect(datesBetween("2030-02-27", "2030-03-02", false)).toEqual([
      "2030-02-27",
      "2030-02-28",
      "2030-03-01",
      "2030-03-02",
    ]);
  });

  it("can leave out the weekend", () => {
    // 1 Mar 2030 is a Friday; 2-3 are the weekend
    expect(datesBetween("2030-03-01", "2030-03-05", true)).toEqual(["2030-03-01", "2030-03-04", "2030-03-05"]);
  });

  it("is empty when the range runs backwards", () => {
    expect(datesBetween("2030-03-05", "2030-03-01", false)).toEqual([]);
  });
});

describe("windowProblem", () => {
  it("accepts separate windows and refuses overlaps, reversed or empty ones", () => {
    expect(windowProblem([{ start: "09:00", end: "11:30" }, { start: "13:00", end: "16:30" }])).toBeNull();
    expect(windowProblem([{ start: "09:00", end: "11:30" }, { start: "11:00", end: "12:00" }])).toMatch(/overlap/);
    expect(windowProblem([{ start: "11:30", end: "09:00" }])).toMatch(/end after/);
    expect(windowProblem([])).toMatch(/at least one/);
  });
});

describe("previewSessions", () => {
  it("lists every date × window and flags the ones the job already has", () => {
    const preview = previewSessions(
      "examination",
      ["2030-03-02", "2030-03-01"],
      [{ start: "13:00", end: "16:30" }, { start: "09:00", end: "11:30" }],
      " room 204 ",
      [slot()]
    );
    expect(preview.map((p) => [p.date, p.start, p.exists])).toEqual([
      ["2030-03-01", "09:00", true],
      ["2030-03-01", "13:00", false],
      ["2030-03-02", "09:00", false],
      ["2030-03-02", "13:00", false],
    ]);
  });
});

describe("hasStarted", () => {
  // 15 Oct 2026, 2:00 PM in the Philippines
  const now = new Date(Date.UTC(2026, 9, 15, 6, 0));

  it("is true for a session already under way or past, false for one to come", () => {
    expect(hasStarted({ date: "2026-10-15", time: "09:00" }, now)).toBe(true);
    expect(hasStarted({ date: "2026-10-14", time: "18:00" }, now)).toBe(true);
    expect(hasStarted({ date: "2026-10-15", time: "16:00" }, now)).toBe(false);
  });
});
