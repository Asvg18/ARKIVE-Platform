/**
 * The display cleaner for text ARKIVE did not word itself: what the AI
 * wrote, and records frozen as they were made. It must take out every
 * long dash, read naturally afterwards, and leave text without one
 * exactly as it was.
 */

import { describe, expect, it } from "vitest";

import { shownText } from "./displayText";

/** The long dash, spelled out so the cases below stay readable. */
const D = "\u2014";

describe("shownText", () => {
  it("leaves text without a long dash exactly as it was", () => {
    const untouched = "Taught Python - and Java - from 2019\u20132021, then moved on.";
    expect(shownText(untouched)).toBe(untouched);
    expect(shownText("")).toBe("");
    expect(shownText(null)).toBeNull();
    expect(shownText(undefined)).toBeUndefined();
  });

  it("turns a dash between words into a comma", () => {
    expect(shownText(`A strong fit ${D} the resume shows six years of teaching.`)).toBe(
      "A strong fit, the resume shows six years of teaching."
    );
    expect(shownText(`Her experience ${D} mostly in retail ${D} does not match.`)).toBe(
      "Her experience, mostly in retail, does not match."
    );
    expect(shownText(`Met${D}the resume lists it.`)).toBe("Met, the resume lists it.");
  });

  it("turns a dash between numbers into a short dash, as a range", () => {
    expect(shownText(`Lecturer, 2019${D}2021`)).toBe("Lecturer, 2019\u20132021");
    expect(shownText(`Scores 3 ${D} 5 across the rubric`)).toBe("Scores 3\u20135 across the rubric");
  });

  it("drops a dash at the start or end of a line, keeping the lines", () => {
    expect(shownText(`${D} Python\n${D} Java`)).toBe("Python\nJava");
    expect(shownText(`Strong on teaching ${D}\nthin on research`)).toBe("Strong on teaching\nthin on research");
  });

  it("drops a dash beside punctuation that already separates", () => {
    expect(shownText(`She said \u201cyes ${D}\u201d and left.`)).toBe("She said \u201cyes\u201d and left.");
    expect(shownText(`Two gaps, ${D} both minor.`)).toBe("Two gaps, both minor.");
    expect(shownText(`Done. ${D} Next, the exam.`)).toBe("Done. Next, the exam.");
    expect(shownText(`A gap (${D} minor) remains.`)).toBe("A gap (minor) remains.");
    expect(shownText(`Unclear ${D}, so a person should read it.`)).toBe("Unclear, so a person should read it.");
  });

  it("treats a run of dashes as one", () => {
    expect(shownText(`Strong ${D}${D} clearly`)).toBe("Strong, clearly");
  });

  it("shows text that is only a dash as an empty value", () => {
    expect(shownText(D)).toBe("\u2013");
    expect(shownText(`  ${D}  `)).toBe("\u2013");
  });

  it("gives frozen records the stage names in use now", () => {
    expect(shownText(`Interview ${D} Dept. Head`)).toBe("Department Head Interview");
    expect(shownText(`Still at Interview ${D} HR Administrator`)).toBe("Still at HR Administrator Interview");
    expect(shownText(`Interview ${D} VP`)).toBe("VP Interview");
  });

  it("shows the AI's “résumé” as “resume”, as ARKIVE's own wording has it", () => {
    expect(shownText("The résumé lists Python. Résumés vary. RÉSUMÉ")).toBe(
      "The resume lists Python. Resumes vary. RESUME"
    );
    expect(shownText(`Met ${D} the résumé lists it.`)).toBe("Met, the resume lists it.");
  });

  it("never leaves a long dash behind", () => {
    const samples = [
      `${D}`,
      `a ${D} b ${D} c`,
      `${D}${D}${D}`,
      `x ${D}\n${D} y`,
      `(${D})`,
      `\u201c${D}\u201d`,
      `1${D}2${D}3`,
      `word${D}`,
    ];
    for (const sample of samples) expect(shownText(sample), sample).not.toContain(D);
  });
});
