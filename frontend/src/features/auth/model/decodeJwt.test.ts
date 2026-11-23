/**
 * Reading the session token the UI decides what to render from.
 *
 * `decodeJwtPayload` deliberately does not verify the signature — the real
 * authorization check is server-side on every request. What matters here is
 * that it never *throws*: it is called during app start-up with whatever is
 * in localStorage, which may be truncated, from an older format, or
 * garbage, and an exception there is a white screen rather than a login
 * prompt.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { decodeJwtPayload, isExpired } from "./decodeJwt";

/** A JWT is three base64url segments; only the middle one is read. */
function makeToken(payload: object): string {
  const body = btoa(JSON.stringify(payload)).replace(/\+/g, "-").replace(/\//g, "_");
  return `header.${body}.signature`;
}

describe("decodeJwtPayload", () => {
  it("reads the payload of a well-formed token", () => {
    const token = makeToken({ user_id: 42, role: "hr_admin", exp: 1893456000 });
    expect(decodeJwtPayload(token)).toEqual({ user_id: 42, role: "hr_admin", exp: 1893456000 });
  });

  it("handles base64url padding characters", () => {
    // '-' and '_' must be translated back to '+' and '/' before atob, or a
    // token containing them decodes to nonsense.
    const payload = { user_id: 1, role: "applicant", exp: 1893456000, note: "a??b>>c" };
    expect(decodeJwtPayload(makeToken(payload))).toEqual(payload);
  });

  it("returns null instead of throwing for anything unreadable", () => {
    for (const bad of ["", "not-a-jwt", "a.b", "a.!!!not-base64!!!.c", "a..c"]) {
      expect(decodeJwtPayload(bad), JSON.stringify(bad)).toBeNull();
    }
  });

  it("returns null when the payload decodes but is not JSON", () => {
    expect(decodeJwtPayload(`header.${btoa("plain text")}.sig`)).toBeNull();
  });
});

describe("isExpired", () => {
  afterEach(() => vi.useRealTimers());

  it("compares the token's seconds against the clock's milliseconds", () => {
    // The classic bug this guards: forgetting the *1000 makes every token
    // look expired, logging everyone out immediately.
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-08T00:00:00Z"));
    const now = Math.floor(Date.now() / 1000);
    expect(isExpired({ user_id: 1, role: "applicant", exp: now + 60 })).toBe(false);
    expect(isExpired({ user_id: 1, role: "applicant", exp: now - 60 })).toBe(true);
  });
});
