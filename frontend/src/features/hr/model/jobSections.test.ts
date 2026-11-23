import { describe, expect, it } from "vitest";
import { cleanSections, sameSections } from "./jobSections";

describe("cleanSections", () => {
  it("trims each section and drops the ones left blank", () => {
    expect(
      cleanSections([
        { title: "  Salary ", content: " Salary Grade 11 " },
        { title: " ", content: "" },
        { title: "", content: "Free parking" },
      ]),
    ).toEqual([
      { title: "Salary", content: "Salary Grade 11" },
      { title: "", content: "Free parking" },
    ]);
  });
});

describe("sameSections", () => {
  const salary = { title: "Salary", content: "Salary Grade 11" };

  it("ignores spacing and blank boxes, as the server does", () => {
    expect(sameSections([{ title: " Salary", content: "Salary Grade 11 " }, { title: "", content: "" }], [salary])).toBe(
      true,
    );
  });

  it("sees an edited, added, removed or reordered section", () => {
    const docs = { title: "Documents", content: "Transcript" };
    expect(sameSections([{ ...salary, content: "Salary Grade 12" }], [salary])).toBe(false);
    expect(sameSections([salary, docs], [salary])).toBe(false);
    expect(sameSections([], [salary])).toBe(false);
    expect(sameSections([docs, salary], [salary, docs])).toBe(false);
  });
});
