import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Account } from "../../../shared/api/account";
import { apiFetch, SESSION_EXPIRED_EVENT, TOKEN_RENEWED_EVENT } from "../../../shared/api/client";
import { decodeJwtPayload, isExpired, type AccessTokenPayload } from "../model/decodeJwt";
import { sessionChangeFromStorage, TOKEN_STORAGE_KEY } from "./sessionSync";

interface AuthContextValue {
  token: string | null;
  /** Set when a session ended on its own rather than by the user
   *  choosing to sign out, so the login screen can say which happened. */
  sessionExpired: boolean;
  user: AccessTokenPayload | null;
  /** The signed-in account's profile — name, photo, email — as the
   *  server reports it. Null while loading or signed out. Held here, not
   *  in each shell, so a change saved on Account Settings shows in the
   *  top bar at once. */
  me: Account | null;
  /** Adopts the account a write returned, or re-reads it. */
  setMe: (account: Account) => void;
  refreshMe: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, fullName: string) => Promise<void>;
  acceptInvite: (inviteToken: string, fullName: string, password: string) => Promise<void>;
  resetPassword: (resetToken: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function loadValidToken(): string | null {
  const stored = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (!stored) return null;
  const payload = decodeJwtPayload(stored);
  if (!payload || isExpired(payload)) {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    return null;
  }
  return stored;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => loadValidToken());
  const [sessionExpired, setSessionExpired] = useState(false);

  const user = useMemo(() => (token ? decodeJwtPayload(token) : null), [token]);
  const [me, setMe] = useState<Account | null>(null);

  const refreshMe = useCallback(async () => {
    if (!token) return;
    try {
      setMe(await apiFetch<Account>("/auth/me", { token }));
    } catch {
      /* the shells fall back to the role name; nothing to break here */
    }
  }, [token]);

  // Keyed on who is signed in, not on the token string: a renewal swaps
  // the token every half hour and must not re-read the same account.
  const userId = user?.user_id ?? null;
  useEffect(() => {
    if (userId == null) {
      setMe(null);
      return;
    }
    void refreshMe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  // apiFetch keeps localStorage current on its own — it writes the
  // renewed token the instant one arrives, and cannot reach React state
  // from a plain function. This picks that up so `user` (and anything
  // derived from the token) reflects the renewal too.
  useEffect(() => {
    /** Picks up a token renewed by apiFetch. Deliberately never clears:
     *  an empty slot here does not mean "signed out", it can also mean a
     *  browser that refuses to store anything (private mode), and
     *  logging someone out on a timer because of that would be worse
     *  than the problem it solves. */
    function adoptRenewedToken() {
      const stored = localStorage.getItem(TOKEN_STORAGE_KEY);
      if (stored && stored !== token) setToken(stored);
    }

    /** Fires only for *other* tabs of this browser, and carries what
     *  changed, so signing out in one tab signs out the rest (on a
     *  shared machine, the next tab must not keep showing the portal).
     *  A removal is acted on from this event, never from the poll, so a
     *  browser that cannot store the token is not mistaken for one that
     *  was signed out of. */
    function onStorageChanged(event: StorageEvent) {
      const change = sessionChangeFromStorage(event, token);
      if (change.action === "sign-out") {
        setToken(null);
        // Another tab *chose* to sign out; the login screen must not
        // claim the session ran out on its own.
        setSessionExpired(false);
      } else if (change.action === "adopt") {
        setToken(change.token);
      }
    }

    /** A renewal that happened in *this* tab. apiFetch has already
     *  stored it; this is what makes the running app use it on the very
     *  next request rather than up to 30 seconds later. */
    function onTokenRenewed(event: Event) {
      const renewed = (event as CustomEvent<string>).detail;
      if (renewed) setToken(renewed);
    }

    function onSessionExpired() {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      setToken(null);
      setSessionExpired(true);
    }

    window.addEventListener("storage", onStorageChanged);
    window.addEventListener(TOKEN_RENEWED_EVENT, onTokenRenewed);
    window.addEventListener(SESSION_EXPIRED_EVENT, onSessionExpired);
    const poll = window.setInterval(adoptRenewedToken, 30_000);
    return () => {
      window.removeEventListener("storage", onStorageChanged);
      window.removeEventListener(TOKEN_RENEWED_EVENT, onTokenRenewed);
      window.removeEventListener(SESSION_EXPIRED_EVENT, onSessionExpired);
      window.clearInterval(poll);
    };
  }, [token]);

  async function login(email: string, password: string) {
    const { access_token } = await apiFetch<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: { email, password },
    });
    localStorage.setItem(TOKEN_STORAGE_KEY, access_token);
    setToken(access_token);
    setSessionExpired(false);
  }

  async function signup(email: string, password: string, fullName: string) {
    await apiFetch("/auth/signup", {
      method: "POST",
      body: { email, password, full_name: fullName },
    });
  }

  async function acceptInvite(inviteToken: string, fullName: string, password: string) {
    const { access_token } = await apiFetch<{ access_token: string }>(`/invites/${inviteToken}/accept`, {
      method: "POST",
      body: { full_name: fullName, password },
    });
    localStorage.setItem(TOKEN_STORAGE_KEY, access_token);
    setToken(access_token);
  }

  /** Spends a password-reset link and leaves the browser signed out. */
  async function resetPassword(resetToken: string, password: string) {
    await apiFetch<void>(
      `/auth/reset-password/${resetToken}`,
      { method: "POST", body: { new_password: password } }
    );
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    setSessionExpired(false);
  }

  function logout() {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    // Signing out deliberately is not an expiry, and must not show the
    // "your session ended" notice.
    setSessionExpired(false);
  }

  return (
    <AuthContext.Provider
      value={{ token, sessionExpired, user, me, setMe, refreshMe, login, signup, acceptInvite, resetPassword, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
