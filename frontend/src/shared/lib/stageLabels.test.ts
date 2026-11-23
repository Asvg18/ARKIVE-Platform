/**
 * The stage vocabulary the whole UI reads stages through.
 *
 * `isInterviewStage` and `isExamStage` are prefix rules that mirror the
 * backend's `app/domain/dfa.py`. That mirroring is the risk worth testing:
 * the two copies are kept in step by hand, and a stage the frontend
 * classifies differently from the server produces a screen that disagrees
 * with the record behind it.
 */

import { describe, expect, it } from "vitest";

import { STAGE_LABELS, STATUS_LABELS, isExamStage, isInterviewStage, jobStageLabel, stageLabel } from "./stageLabels";

describe("stageLabel", () => {
  it("renders the short dash for no stage, so a terminal application shows something", () => {
    expect(stageLabel(null)).toBe("\u2013");
  });

  it("falls back to the raw stage name rather than rendering blank", () => {
    // A stage added to the backend before the frontend knows about it must
    // still be readable — degraded, not empty.
    expect(stageLabel("some_future_stage")).toBe("some_future_stage");
  });

  it("uses the friendly label for a known stage", () => {
    expect(stageLabel("skill_matching")).toBe("Pre-Screening");
    expect(stageLabel("document_upload")).toBe("Document Upload");
  });
});

describe("jobStageLabel", () => {
  const job = {
    interview_round_labels: { interview_round_1: "Panel Interview", interview_round_2: "" },
    examination_labels: { examination_1: "Technical Exam" },
  };

  it("uses the name HR gave the round or exam for this job", () => {
    expect(jobStageLabel("interview_round_1", job)).toBe("Panel Interview");
    expect(jobStageLabel("examination_1", job)).toBe("Technical Exam");
  });

  it("treats a blank name as no name, as the backend does", () => {
    // resolve_stage_label() uses `or`, so an emptied field falls back;
    // `??` here would have rendered an empty row instead.
    expect(jobStageLabel("interview_round_2", job)).toBe("Interview Round 2");
  });

  it("falls back to the static label, with or without a job", () => {
    expect(jobStageLabel("shortlisting", job)).toBe("Shortlisting");
    expect(jobStageLabel("shortlisting", null)).toBe("Shortlisting");
    expect(jobStageLabel(null, job)).toBe("\u2013");
  });
});

describe("isInterviewStage", () => {
  it("matches both the generic rounds and the legacy fixed slots", () => {
    // Legacy names still exist on in-flight applications; misclassifying
    // one would hide its scorecard from the interview tab.
    for (const stage of [
      "interview_round_1",
      "interview_round_6",
      "interview_hr_director",
      "interview_dept_head",
      "interview_vp",
    ]) {
      expect(isInterviewStage(stage), stage).toBe(true);
    }
  });

  it("does not match non-interview stages or null", () => {
    for (const stage of ["examination", "final_decision", "document_upload", null]) {
      expect(isInterviewStage(stage), String(stage)).toBe(false);
    }
  });
});

describe("isExamStage", () => {
  it("matches the legacy singular slot and the numbered ones", () => {
    for (const stage of ["examination", "examination_1", "examination_4"]) {
      expect(isExamStage(stage), stage).toBe(true);
    }
  });

  it("does not match null or an unrelated stage", () => {
    expect(isExamStage(null)).toBe(false);
    expect(isExamStage("interview_round_1")).toBe(false);
  });
});

describe("the label tables", () => {
  it("classifies every interview and examination key it defines", () => {
    // Guards the prefix rules against a future label whose key does not
    // follow the naming convention the rules depend on.
    for (const key of Object.keys(STAGE_LABELS)) {
      if (key.startsWith("interview_")) expect(isInterviewStage(key), key).toBe(true);
      if (key.startsWith("examination")) expect(isExamStage(key), key).toBe(true);
    }
  });

  it("shows an accepted candidate as Accepted, not Hired", () => {
    // The enum value stays `hired`; only the displayed word is "Accepted".
    expect(STATUS_LABELS.hired).toBe("Accepted");
  });

  it("has a label for every application status the API can return", () => {
    for (const status of ["active", "rejected", "hired", "flagged", "withdrawn"]) {
      expect(STATUS_LABELS[status], status).toBeTruthy();
    }
  });
});
