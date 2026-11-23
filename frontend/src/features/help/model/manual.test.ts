import { describe, expect, it } from "vitest";
import source from "./manual.md?raw";
import { MANUAL, PAGE_TOPIC_IDS, helpTopicFor, manualFor, parseManual, searchManual, slugify } from "./manual";

const allIds = (sections = MANUAL) => sections.flatMap((s) => [s.id, ...s.topics.map((t) => t.id)]);

describe("the manual", () => {
  it("reads every section of the document", () => {
    expect(MANUAL.map((s) => s.label ?? s.title)).toEqual([
      "Section 1",
      "Section 2",
      "Section 3",
      "Section 4",
      "Section 5",
      "Section 6",
      "Section 7",
      "Conclusion",
    ]);
  });

  it("gives every section and topic its own address", () => {
    const ids = allIds();
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("reads tables, lists and paragraphs", () => {
    const roles = MANUAL[0].topics.find((t) => t.id === "user-roles")!;
    const table = roles.blocks.find((b) => b.kind === "table");
    expect(table).toMatchObject({ head: ["Role", "Portal", "What they do", "How they get an account"] });
    expect(table?.kind === "table" && table.rows.map((r) => r[0])).toEqual([
      "Applicant",
      "HR Admin",
      "Super Admin",
      "Evaluator",
    ]);

    const onboarding = MANUAL.flatMap((s) => s.topics).find((t) => t.id === "onboarding")!;
    expect(onboarding.blocks.map((b) => b.kind)).toEqual(["p", "check"]);
  });

  it("has no long dash, the same rule as every other screen", () => {
    expect(source).not.toContain("—");
  });

  it("drops the numbers from addresses so renumbering keeps links working", () => {
    expect(slugify("3.6 Booking an Exam")).toBe("booking-an-exam");
    expect(slugify("Section 4: HR Admin Guide")).toBe("hr-admin-guide");
    expect(slugify("4.5 Working the Pipeline (HR Workflow)")).toBe("working-the-pipeline-hr-workflow");
  });

  it("keeps a paragraph that follows a list apart from it", () => {
    const [list, paragraph] = parseManual("## A\n\n1. one\n2. two\nAfter.").at(0)!.blocks;
    expect(list).toEqual({ kind: "ol", items: ["one", "two"] });
    expect(paragraph).toEqual({ kind: "p", text: "After." });
  });
});

describe("what each role sees", () => {
  it("shows a role its own guide and FAQ, and leaves the others out", () => {
    const hr = manualFor("hr");
    expect(hr.map((s) => s.id)).toContain("hr-admin-guide");
    expect(hr.map((s) => s.id)).not.toContain("applicant-guide");
    expect(hr.map((s) => s.id)).not.toContain("evaluator-guide");

    const faq = hr.find((s) => s.id === "frequently-asked-questions-and-troubleshooting")!;
    expect(faq.topics.map((t) => t.id)).toEqual(["signing-in-and-accounts", "hr-admins"]);
  });

  it("shows everything to someone signed out", () => {
    expect(manualFor(null)).toBe(MANUAL);
  });
});

describe("each portal's numbering", () => {
  const words = (role: "applicant" | "hr" | "evaluator") =>
    JSON.stringify(manualFor(role).map((s) => [s.label, s.blocks, s.topics]));

  it.each(["applicant", "hr", "evaluator"] as const)("runs 1 to 5 with no gaps for %s", (role) => {
    expect(manualFor(role).map((s) => s.label)).toEqual([
      "Section 1",
      "Section 2",
      "Section 3",
      "Section 4",
      "Section 5",
      null,
    ]);
  });

  it("puts the role's own guide third and numbers its topics to match", () => {
    const hr = manualFor("hr");
    expect(hr[2].title).toBe("HR Admin Guide");
    expect(hr[2].topics.map((t) => t.title.split(" ")[0])).toEqual(
      ["3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8", "3.9"]
    );
    expect(manualFor("evaluator")[2].topics[0].title).toBe("3.1 Your Review Queue");
  });

  it("follows the new numbers in the text, never naming a section the reader lacks", () => {
    const hr = words("hr");
    expect(hr).toContain("(section 3.3)");
    expect(hr).toContain("(section 3.9)");
    expect(hr).toContain("see section 4");
    expect(hr).toContain("check Section 4 if");
    expect(hr).toContain("**Section 5:** ARKIVE's terms");
    for (const role of ["applicant", "hr", "evaluator"] as const) {
      expect(words(role)).not.toMatch(/[Ss]ections? [67]\b|[Ss]ections? [4-9]\.\d/);
    }
  });

  it("names only the reader's own guide in How to Use This Manual", () => {
    const howTo = manualFor("evaluator")[0].topics.find((t) => t.id === "how-to-use-this-manual")!;
    const list = howTo.blocks.find((b) => b.kind === "ul");
    expect(list?.kind === "ul" && list.items[1]).toBe(
      "**Section 3, Evaluator Guide:** step-by-step instructions for your role."
    );
  });
});

describe("search", () => {
  it("keeps only the topics with every word", () => {
    const found = searchManual(MANUAL, "offer deadline");
    const topics = found.flatMap((s) => s.topics.map((t) => t.id));
    expect(topics).toContain("responding-to-a-job-offer");
    expect(topics).not.toContain("setting-your-availability");
  });

  it("matches words inside the bold button names", () => {
    expect(searchManual(MANUAL, "save score").flatMap((s) => s.topics.map((t) => t.id))).toContain(
      "exams-and-interviews"
    );
  });

  it("finds nothing for a word the manual never uses", () => {
    expect(searchManual(MANUAL, "zzzz")).toEqual([]);
  });
});

describe("the ? button", () => {
  it("points every page at a topic that exists", () => {
    const ids = new Set(allIds());
    expect(PAGE_TOPIC_IDS.filter((id) => !ids.has(id))).toEqual([]);
  });

  it("finds the topic for the page", () => {
    expect(helpTopicFor("/applicant/jobs")).toBe("finding-a-job");
    expect(helpTopicFor("/hr")).toBe("the-hr-dashboard");
    expect(helpTopicFor("/hr/requisitions/12/workflow")).toBe("setting-the-hiring-workflow");
    expect(helpTopicFor("/hr/applications/5/pre-201-package")).toBe("final-decision-offer-and-pre-201");
    expect(helpTopicFor("/hr/applications/5")).toBe("working-the-pipeline-hr-workflow");
    expect(helpTopicFor("/evaluator/interviews/9")).toBe("scoring-the-interview");
    expect(helpTopicFor("/evaluator/account")).toBe("account-settings");
    expect(helpTopicFor("/help")).toBeNull();
  });
});
