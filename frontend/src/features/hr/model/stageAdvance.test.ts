/**
 * Which advances ask "Are you sure?" first: all of them.
 */

import { describe, expect, it } from "vitest";
import { asksBeforeAdvancing } from "./stageAdvance";

describe("asksBeforeAdvancing", () => {
  it("asks before every stage", () => {
    for (const stage of [
      "skill_matching",
      "shortlisting",
      "examination",
      "examination_2",
      "interview_round_1",
      "interview_vp",
      "final_decision",
      "onboarding",
    ]) {
      expect(asksBeforeAdvancing(stage)).toBe(true);
    }
  });

  it("has nothing to ask with no next stage", () => {
    expect(asksBeforeAdvancing(null)).toBe(false);
  });
});
