import { describe, expect, it } from "vitest";
import { interviewDurations, interviewMinutes, withInterviewDurations } from "./interviewMinutes";
import { makeStage } from "./workflowStages";

describe("interview lengths in the workflow editor", () => {
  it("starts each round on the old defaults: 45 minutes for rounds 1–2, 30 after", () => {
    expect(interviewMinutes(makeStage("interview_round_1"))).toBe(45);
    expect(interviewMinutes(makeStage("interview_round_3"))).toBe(30);
  });

  it("saves minutes for interview rounds only", () => {
    const stages = [makeStage("document_upload"), { ...makeStage("interview_round_1"), minutes: 60 }];
    expect(interviewDurations(stages)).toEqual({ interview_round_1: 60 });
  });

  it("puts a job's saved lengths back on its stages", () => {
    const [round] = withInterviewDurations([makeStage("interview_round_2")], { interview_round_2: 90 });
    expect(interviewMinutes(round)).toBe(90);
  });
});
