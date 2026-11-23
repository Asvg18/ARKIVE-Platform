/**
 * Turning a failed response into a sentence someone can act on.
 *
 * FastAPI's default 422 body is a *list* of {loc, msg, type} objects; a
 * list is typeof "object" but has no .message, so it fell through to
 * res.statusText -- the empty string over HTTP/2, i.e. everywhere
 * behind Caddy in production. The Workflow Builder's only validation is
 * exactly that shape, so "Save Workflow" appeared to do nothing. These
 * cases pin all three shapes so the list branch can't quietly regress.
 */

import { describe, expect, it } from "vitest";

import { ApiError, messageFromDetail } from "./client";

const FALLBACK = "Something went wrong.";

describe("messageFromDetail", () => {
  it("passes a plain string detail straight through", () => {
    expect(messageFromDetail("Job not found.", FALLBACK)).toBe("Job not found.");
  });

  it("reads .message off a structured gate refusal", () => {
    const detail = { code: "stage_incomplete", message: "Record the exam score first.", blockers: [] };
    expect(messageFromDetail(detail, FALLBACK)).toBe("Record the exam score first.");
  });

  it("joins a Pydantic validation list — the W2 regression", () => {
    const detail = [{ loc: ["body", "workflow"], msg: "Duplicate stage: document_upload", type: "value_error" }];
    expect(messageFromDetail(detail, FALLBACK)).toBe("Duplicate stage: document_upload");
  });

  it("strips Pydantic's 'Value error, ' prefix so the author's sentence shows", () => {
    const detail = [{ msg: "Value error, A workflow needs at least one stage." }];
    expect(messageFromDetail(detail, FALLBACK)).toBe("A workflow needs at least one stage.");
  });

  it("joins multiple validation messages", () => {
    const detail = [{ msg: "First problem." }, { msg: "Second problem." }];
    expect(messageFromDetail(detail, FALLBACK)).toBe("First problem. Second problem.");
  });

  it("falls back rather than returning an empty string", () => {
    // The actual production symptom: a blank message renders as nothing at
    // all, so the button looks broken instead of refused.
    for (const detail of [null, undefined, "", "   ", [], [{ loc: ["body"] }], {}, { message: 42 }]) {
      expect(messageFromDetail(detail, FALLBACK), JSON.stringify(detail)).toBe(FALLBACK);
    }
  });
});

describe("ApiError", () => {
  it("keeps the structured detail alongside the readable message", () => {
    const detail = { code: "stage_incomplete", blockers: [{ label: "Exam score" }] };
    const err = new ApiError(409, "Stage incomplete.", detail);
    expect(err).toBeInstanceOf(Error);
    expect(err.status).toBe(409);
    expect(err.message).toBe("Stage incomplete.");
    expect(err.detail).toEqual(detail);
  });
});
