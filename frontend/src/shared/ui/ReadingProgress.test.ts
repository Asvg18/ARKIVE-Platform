import { describe, expect, it } from "vitest";
import { announcement, estimatedPercent, stepsDone } from "./ReadingProgress";

describe("estimatedPercent", () => {
  it("starts at zero and climbs", () => {
    expect(estimatedPercent(0, 20_000)).toBe(0);
    expect(estimatedPercent(10_000, 20_000)).toBeGreaterThan(30);
  });

  it("never passes 90% on its own, however long it runs", () => {
    expect(estimatedPercent(10 * 60_000, 20_000)).toBeLessThanOrEqual(90);
  });
});

const steps = [
  { label: "Contact details", until: 15 },
  { label: "Education", until: 35 },
  { label: "Work experience", until: 55 },
  { label: "Skills and certifications", until: 75 },
];

describe("stepsDone", () => {
  it("ticks each step as the estimate passes it, and none before", () => {
    expect(stepsDone(0, steps)).toBe(0);
    expect(stepsDone(14, steps)).toBe(0);
    expect(stepsDone(15, steps)).toBe(1);
    expect(stepsDone(56, steps)).toBe(3);
  });

  it("leaves the last step for the real response when it sits past 90%", () => {
    const submit = [
      { label: "Saving your application", until: 12 },
      { label: "Matching your skills to the job", until: 100 },
    ];
    expect(stepsDone(estimatedPercent(10 * 60_000, 25_000), submit)).toBe(1);
  });
});

describe("announcement", () => {
  it("speaks once per finished step, then once when done", () => {
    expect(announcement("Reading your resume", steps, 0, false)).toBe("");
    expect(announcement("Reading your resume", steps, 2, false)).toBe("Education: done.");
    expect(announcement("Reading your resume", steps, 4, true)).toBe("Reading your resume: done.");
  });
});
