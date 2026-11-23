import { describe, expect, it } from "vitest";
import { afterSignInPath } from "./roleHome";

describe("afterSignInPath", () => {
  it("honours a path inside the role's own portal", () => {
    expect(afterSignInPath("applicant", "/applicant/jobs?q=librarian")).toBe("/applicant/jobs?q=librarian");
    expect(afterSignInPath("applicant", "/applicant")).toBe("/applicant");
  });

  it("falls back to the role's home for anything else", () => {
    expect(afterSignInPath("applicant", null)).toBe("/applicant");
    expect(afterSignInPath("applicant", "https://evil.example/applicant")).toBe("/applicant");
    expect(afterSignInPath("applicant", "//evil.example/applicant")).toBe("/applicant");
    expect(afterSignInPath("applicant", "/\\evil.example")).toBe("/applicant");
    expect(afterSignInPath("applicant", "/hr/pipelines")).toBe("/applicant");
    expect(afterSignInPath("applicant", "/applicantfoo")).toBe("/applicant");
    expect(afterSignInPath("hr_admin", "/applicant/jobs")).toBe("/hr");
  });
});
