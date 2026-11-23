/** What a `storage` event from another tab means for this one, as a pure
 * function of (what changed, what we hold). Exported for its own tests,
 * like decodeJwt, because a wrong branch here is silent: a missing
 * sign-out branch would leave every other tab holding a working token. */

export const TOKEN_STORAGE_KEY = "arkive_token";

export type SessionChange =
  /** Another tab signed out. Not an expiry -- the login screen must not
   *  claim the session ran out when someone chose to end it. */
  | { action: "sign-out" }
  /** Another tab signed in, or apiFetch renewed the token there. */
  | { action: "adopt"; token: string }
  | { action: "ignore" };

export function sessionChangeFromStorage(
  event: Pick<StorageEvent, "key" | "newValue">,
  currentToken: string | null
): SessionChange {
  // A null key means the whole store was cleared (localStorage.clear(),
  // or the browser clearing site data), which takes the token with it.
  if (event.key !== null && event.key !== TOKEN_STORAGE_KEY) return { action: "ignore" };

  if (event.newValue === null) {
    // Already signed out here; nothing to do rather than a redundant
    // state write on every unrelated tab.
    return currentToken === null ? { action: "ignore" } : { action: "sign-out" };
  }

  return event.newValue === currentToken
    ? { action: "ignore" }
    : { action: "adopt", token: event.newValue };
}
