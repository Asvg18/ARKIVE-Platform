export const BASE_URL = import.meta.env.VITE_API_BASE_URL;

/** Where the access token lives. Declared here as well as in AuthContext
 *  because apiFetch has to write a renewed token the moment it arrives —
 *  it cannot reach into React state from a plain function. */
const TOKEN_STORAGE_KEY = "arkive_token";

/** Header the API sets when it hands back a fresh token (see
 *  backend/app/infra/deps.py). Must stay in step with that constant. */
const RENEWED_TOKEN_HEADER = "X-Renewed-Token";

/** Fired when the server rejects our credentials, so AuthContext can end
 *  the session cleanly instead of leaving every screen to surface its own
 *  raw error. A custom event rather than a direct call because this
 *  module is deliberately React-free. */
export const SESSION_EXPIRED_EVENT = "arkive:session-expired";

/** Fired the moment a renewed token is stored, so AuthContext adopts it
 *  at once instead of at its next poll. It matters after a password
 *  change, which ends every older session: the outgoing token is
 *  already dead, so one more request with it would sign the person out.
 *  An event, not a direct call, because this module stays React-free. */
export const TOKEN_RENEWED_EVENT = "arkive:token-renewed";

export class ApiError extends Error {
  status: number;
  /**
   * The raw `detail` from the response body, for the endpoints that
   * return a structured one rather than a sentence (the hire gate's 409
   * carries the list of what is missing). `message` stays a string for
   * the many call sites that render it directly — a structured detail
   * would otherwise reach them as "[object Object]".
   */
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Turns a failed response's `detail` into a sentence a person can read.
 *
 * Handles the three shapes FastAPI sends: a plain string
 * (HTTPException), an object with its own `message` (the stage gate's
 * 409), and a list of {loc, msg, type} (the default 422 validation
 * error). Pydantic v2's "Value error, " prefix is stripped so the
 * validator's own sentence shows. Returns `fallback` when none is usable.
 */
// exported so its tests can pin the list case directly
export function messageFromDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) return detail;

  if (Array.isArray(detail)) {
    const msgs = detail
      .map((item) =>
        item && typeof item === "object" && typeof (item as { msg?: unknown }).msg === "string"
          ? (item as { msg: string }).msg.replace(/^Value error,\s*/i, "")
          : null
      )
      .filter((m): m is string => m !== null && m.trim() !== "");
    if (msgs.length > 0) return msgs.join(" ");
  }

  if (detail && typeof detail === "object" && typeof (detail as { message?: unknown }).message === "string") {
    return (detail as { message: string }).message;
  }

  return fallback;
}

const DEFAULT_TIMEOUT_MS = 15_000;

/** For requests that wait on the AI agents (resume extraction, skill
 *  matching, pre-screening), which routinely run past 15s. A client-side
 *  abort does not stop the server, which finishes and commits anyway, so
 *  a short timeout would report a submission that succeeded as failed. */
export const AI_REQUEST_TIMEOUT_MS = 120_000;

export async function apiFetch<T>(
  path: string,
  options: { method?: string; body?: unknown; token?: string | null; timeoutMs?: number } = {}
): Promise<T> {
  const isFormData = options.body instanceof FormData;
  const headers: Record<string, string> = {};
  if (!isFormData) headers["Content-Type"] = "application/json";
  if (options.token) headers["Authorization"] = `Bearer ${options.token}`;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: isFormData ? (options.body as FormData) : options.body ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });
  } catch (err) {
    // fetch() itself throws (not an ApiError) for two reasons worth
    // telling apart: our own timeout abort above, vs. the server/network
    // being genuinely unreachable. normalizing both into ApiError means
    // every call site's `err instanceof ApiError ? err.message : "..."`
    // fallback shows specific, actionable text with no per-page changes.
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, "Request timed out. Check your connection and try again.");
    }
    throw new ApiError(0, "Could not reach the server. Check your connection and try again.");
  } finally {
    clearTimeout(timeout);
  }

  // the API slides the session forward while someone is working: past
  // the halfway point of a token's life it returns a replacement, swapped
  // in silently. without this the session ends at a hard 60-minute
  // cliff regardless of activity.
  const renewed = res.headers.get(RENEWED_TOKEN_HEADER);
  if (renewed) {
    try {
      localStorage.setItem(TOKEN_STORAGE_KEY, renewed);
    } catch {
      // Private browsing and similar can refuse writes. A failed renewal
      // is not worth failing the request over — the session simply does
      // not survive a reload.
    }
    // Outside the try on purpose: a browser that refuses to store the
    // token can still use it for the rest of this page's life, and the
    // renewal matters most in the one case where the outgoing token is
    // already dead (a password change).
    window.dispatchEvent(new CustomEvent(TOKEN_RENEWED_EVENT, { detail: renewed }));
  }

  if (res.status === 401) {
    // genuinely expired or revoked -- announce it once, centrally, so
    // the user lands back on login with an explanation instead of
    // watching unrelated errors on whatever page they were on. the throw
    // still happens, so callers' own error paths are unaffected.
    window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT));
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    // `res.statusText` is the empty string over HTTP/2, so it can't be the
    // last resort on its own — a status-coded sentence is, so an error is
    // never rendered blank no matter its shape.
    const message = messageFromDetail(detail, res.statusText || `Request failed (${res.status}).`);
    throw new ApiError(res.status, message, detail);
  }
  // A response with no body (204, or the 202 from /auth/forgot-password,
  // which must look the same whether or not the address has an account)
  // has nothing to parse; .json() would throw on it. Decided by reading
  // the body, not by listing statuses.
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

/** Fetches an authenticated, non-JSON GET (a PDF, typically) and hands
 * back a local blob: URL for it. apiFetch can't be reused here -- it
 * always parses the response as JSON -- and the token can't travel as a
 * URL query param (never put auth/session data in a URL), so this
 * fetches with an Authorization header instead.
 *
 * The caller owns the returned URL and must revoke it (URL.
 * revokeObjectURL) once done with it -- unlike openFile's own
 * fire-and-forget new tab, there's no one lifetime that fits every
 * caller (an inline preview needs the URL alive for as long as it's on
 * screen, which a fixed timeout can't know in advance). */
export async function fetchFileBlobUrl(path: string, token: string | null, errorMessage = "Could not load the file."): Promise<string> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) {
    throw new Error(errorMessage);
  }
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

/** Opens an authenticated, non-JSON GET (a PDF, typically) in a new tab.
 * Fire-and-forget, so the object URL only needs to survive long enough
 * for the new tab to load it -- 30s is generous slack for that. */
export async function openFile(path: string, token: string | null, errorMessage = "Could not download the file."): Promise<void> {
  const url = await fetchFileBlobUrl(path, token, errorMessage);
  window.open(url, "_blank", "noopener,noreferrer");
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

/** Triggers a real browser download (a save, not a new tab) for an
 * authenticated GET -- for a file type with no in-browser viewer (an
 * .xlsx, say), window.open on a blob: URL just does nothing visible.
 * The server's own Content-Disposition filename has no effect on a
 * blob fetched this way (that header only matters for a direct
 * navigation), so `filename` is what the browser actually saves it as. */
export async function downloadFile(path: string, token: string | null, filename: string, errorMessage = "Could not download the file."): Promise<void> {
  const url = await fetchFileBlobUrl(path, token, errorMessage);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}
