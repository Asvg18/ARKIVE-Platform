import type { AccountRole } from "../../../shared/api/account";

export interface AccessTokenPayload {
  user_id: number;
  role: AccountRole;
  exp: number;
}

/**
 * Reads a JWT's payload WITHOUT verifying its signature. That's fine here —
 * the payload is only ever used to decide what the UI shows (nav, which
 * dashboard to redirect to). The actual authorization check happens
 * server-side on every request against the live DB row, so a forged
 * payload here can change what a user *sees*, never what they can *do*.
 */
export function decodeJwtPayload(token: string): AccessTokenPayload | null {
  try {
    const [, payloadSegment] = token.split(".");
    const base64 = payloadSegment.replace(/-/g, "+").replace(/_/g, "/");
    const json = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + c.charCodeAt(0).toString(16).padStart(2, "0"))
        .join("")
    );
    return JSON.parse(json);
  } catch {
    return null;
  }
}

export function isExpired(payload: AccessTokenPayload): boolean {
  return payload.exp * 1000 < Date.now();
}
