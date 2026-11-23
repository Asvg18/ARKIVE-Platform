/**
 * Telling the sufficiency gate's refusal apart from every other 409.
 *
 * The discrimination matters in both directions, which is why it is worth
 * its own tests: miss the gate and HR sees a dead-end error where an
 * override was on offer; over-match it and an unrelated conflict opens a
 * dialog inviting HR to override a rule that has no override.
 */

import { describe, expect, it } from "vitest";

import { ApiError } from "../api/client";
import { stageGateRefusal } from "./stageGate";

const BLOCKERS = [{ code: "missing_score", label: "Examination score" }];

function gateError(detail: unknown) {
  return new ApiError(409, "Stage incomplete.", detail);
}

describe("stageGateRefusal", () => {
  it("recognises the gate and returns its message and blockers", () => {
    const err = gateError({ code: "stage_incomplete", message: "Record the exam score.", blockers: BLOCKERS });
    expect(stageGateRefusal(err)).toEqual({ message: "Record the exam score.", blockers: BLOCKERS });
  });

  it("defaults a missing message and blockers rather than returning undefined", () => {
    expect(stageGateRefusal(gateError({ code: "stage_incomplete" }))).toEqual({ message: null, blockers: [] });
  });

  it("ignores a 409 that is not the gate", () => {
    // Keyed on `code`, never the status alone.
    expect(stageGateRefusal(gateError({ code: "already_hired" }))).toBeNull();
    expect(stageGateRefusal(gateError("Someone else moved this candidate."))).toBeNull();
    expect(stageGateRefusal(gateError(null))).toBeNull();
  });

  it("ignores the gate's own code on a different status", () => {
    expect(stageGateRefusal(new ApiError(400, "x", { code: "stage_incomplete" }))).toBeNull();
    expect(stageGateRefusal(new ApiError(422, "x", { code: "stage_incomplete" }))).toBeNull();
  });

  it("ignores things that are not ApiErrors at all", () => {
    for (const err of [new Error("boom"), "a string", null, undefined, { status: 409 }]) {
      expect(stageGateRefusal(err), String(err)).toBeNull();
    }
  });
});
