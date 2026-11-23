import { describe, expect, it } from "vitest";
import { sessionChangeFromStorage, TOKEN_STORAGE_KEY } from "./sessionSync";

const TOKEN = "header.payload.signature";

describe("sessionChangeFromStorage", () => {
  it("signs this tab out when another tab clears the token", () => {
    // The branch that did not exist. Signing out in one tab left every
    // other tab rendering the portal, still holding a working token in
    // memory -- so someone signing out on a shared machine and walking
    // away left their data on screen in the next tab along.
    expect(
      sessionChangeFromStorage({ key: TOKEN_STORAGE_KEY, newValue: null }, TOKEN)
    ).toEqual({ action: "sign-out" });
  });

  it("adopts a token another tab just wrote", () => {
    expect(
      sessionChangeFromStorage({ key: TOKEN_STORAGE_KEY, newValue: TOKEN }, null)
    ).toEqual({ action: "adopt", token: TOKEN });
  });

  it("adopts a renewed token that replaced the one we hold", () => {
    expect(
      sessionChangeFromStorage({ key: TOKEN_STORAGE_KEY, newValue: "newer.token.here" }, TOKEN)
    ).toEqual({ action: "adopt", token: "newer.token.here" });
  });

  it("ignores a write of the token we already hold", () => {
    expect(
      sessionChangeFromStorage({ key: TOKEN_STORAGE_KEY, newValue: TOKEN }, TOKEN)
    ).toEqual({ action: "ignore" });
  });

  it("ignores a sign-out when this tab is already signed out", () => {
    expect(
      sessionChangeFromStorage({ key: TOKEN_STORAGE_KEY, newValue: null }, null)
    ).toEqual({ action: "ignore" });
  });

  it("ignores changes to unrelated keys", () => {
    // Anything else the app or an extension keeps in localStorage must
    // not be able to end a session.
    expect(
      sessionChangeFromStorage({ key: "some-other-key", newValue: null }, TOKEN)
    ).toEqual({ action: "ignore" });
  });

  it("treats the whole store being cleared as a sign-out", () => {
    // localStorage.clear() and a browser clearing site data both arrive
    // as a null key, and both take the token with them.
    expect(sessionChangeFromStorage({ key: null, newValue: null }, TOKEN)).toEqual({
      action: "sign-out",
    });
  });
});
