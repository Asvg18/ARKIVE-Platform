import { describe, expect, it } from "vitest";
import {
  INVITE_FIELDS,
  inviteErrorFromServer,
  joinFullName,
  signupErrorFromServer,
  validateSignup,
  validateSignupField,
  type SignupValues,
} from "./signupValidation";

const valid: SignupValues = {
  firstName: "Juan",
  lastName: "Dela Cruz",
  email: "juan@example.com",
  password: "a-long-passphrase",
  confirmPassword: "a-long-passphrase",
};

describe("validateSignup", () => {
  it("passes a complete, consistent form", () => {
    expect(validateSignup(valid)).toEqual({});
  });

  it("names every empty field", () => {
    const errors = validateSignup({ firstName: "", lastName: " ", email: "", password: "", confirmPassword: "" });
    expect(errors).toEqual({
      firstName: "Enter your first name.",
      lastName: "Enter your last name.",
      email: "Enter your email address.",
      password: "Create a password.",
      confirmPassword: "Confirm your password.",
    });
  });
});

describe("names", () => {
  it.each(["Niño", "Ma. Cristina", "Dela Cruz-Santos", "O'Brien", "Zoë", "D’Angelo"])("accepts %s", (name) => {
    expect(validateSignupField("firstName", { ...valid, firstName: name })).toBeUndefined();
  });

  it.each(["Juan2", "@juan", "-Juan", "Juan!"])("refuses %s", (name) => {
    expect(validateSignupField("lastName", { ...valid, lastName: name })).toBe(
      "Last name can't contain numbers or symbols."
    );
  });

  it("caps the length", () => {
    expect(validateSignupField("firstName", { ...valid, firstName: "a".repeat(101) })).toBe(
      "First name must be 100 characters or fewer."
    );
  });

  it("joins them the way the account stores one name", () => {
    expect(joinFullName("  Ma.  Cristina ", " Dela   Cruz ")).toBe("Ma. Cristina Dela Cruz");
  });
});

describe("email", () => {
  it.each(["juan", "juan@", "juan@example", "juan @example.com"])("refuses %s", (email) => {
    expect(validateSignupField("email", { ...valid, email })).toBe("Enter a valid email address, like name@example.com.");
  });
});

describe("password", () => {
  it("wants at least 8 characters", () => {
    expect(validateSignupField("password", { ...valid, password: "short" })).toBe("Password must be at least 8 characters.");
  });

  it("stops at bcrypt's 72", () => {
    expect(validateSignupField("password", { ...valid, password: "x".repeat(73) })).toBe(
      "Password must be 72 characters or fewer."
    );
  });

  it("may not be the email address", () => {
    expect(validateSignupField("password", { ...valid, password: "Juan@Example.com" })).toBe(
      "Password can't be the same as your email address."
    );
  });

  it("must be typed the same twice", () => {
    expect(validateSignupField("confirmPassword", { ...valid, confirmPassword: "a-long-passphrasE" })).toBe(
      "Passwords don't match."
    );
  });
});

describe("signupErrorFromServer", () => {
  it("puts a registered address on the email field", () => {
    expect(signupErrorFromServer(409, "A user with this email already exists.", "")).toEqual({
      field: "email",
      message: "An account with this email address already exists.",
      kind: "duplicate-email",
    });
  });

  it("passes the server's common-password sentence through to the password field", () => {
    const detail = [
      {
        loc: ["body", "password"],
        msg: "Value error, That password is one of the most commonly used ones. Please choose something less guessable.",
      },
    ];
    expect(signupErrorFromServer(422, detail, "")).toEqual({
      field: "password",
      message: "That password is one of the most commonly used ones. Please choose something less guessable.",
    });
  });

  it("replaces the validator library's email wording", () => {
    const detail = [{ loc: ["body", "email"], msg: "value is not a valid email address: The domain name x is not valid." }];
    expect(signupErrorFromServer(422, detail, "")).toEqual({
      field: "email",
      message: "Enter a valid email address, like name@example.com.",
    });
  });

  it("keeps the server's own sentence for a rate limit and a lost connection", () => {
    expect(signupErrorFromServer(429, null, "Too many accounts… Try again in 12 minute(s).")).toEqual({
      message: "Too many accounts… Try again in 12 minute(s).",
    });
    expect(signupErrorFromServer(0, null, "Could not reach the server.")).toEqual({ message: "Could not reach the server." });
  });

  it("does not show a server fault's internals", () => {
    expect(signupErrorFromServer(500, null, "Internal Server Error")).toEqual({
      message: "Something went wrong on our side. Please try again in a moment.",
    });
  });
});

describe("accepting an invitation", () => {
  it("asks for the same fields as sign-up, less the email the invitation fixed", () => {
    expect(validateSignup({ ...valid, email: "" }, INVITE_FIELDS)).toEqual({});
    const errors = validateSignup(
      { firstName: "", lastName: "", email: "juan@example.com", password: "", confirmPassword: "" },
      INVITE_FIELDS
    );
    expect(errors).toEqual({
      firstName: "Enter your first name.",
      lastName: "Enter your last name.",
      password: "Create a password.",
      confirmPassword: "Confirm your password.",
    });
  });

  it("still refuses the invited address as the password", () => {
    expect(validateSignup({ ...valid, password: "juan@example.com", confirmPassword: "juan@example.com" }, INVITE_FIELDS)).toEqual({
      password: "Password can't be the same as your email address.",
    });
  });

  it("says over the button when the invitation itself stopped working", () => {
    expect(inviteErrorFromServer(409, "This invite is revoked, not pending.", "This invite is revoked, not pending.")).toEqual({
      message: "This invite is revoked, not pending.",
    });
    expect(inviteErrorFromServer(409, "A user with this email already exists.", "A user with this email already exists.")).toEqual({
      message: "A user with this email already exists.",
    });
    expect(inviteErrorFromServer(404, "Invite not found", "Invite not found")).toEqual({
      message: "This invitation link was replaced by a newer one. Use the most recent link you were sent.",
    });
  });

  it("puts a refused password on the password field, as sign-up does", () => {
    const detail = [
      {
        loc: ["body", "password"],
        msg: "Value error, That password is one of the most commonly used ones. Please choose something less guessable.",
      },
    ];
    expect(inviteErrorFromServer(422, detail, "")).toEqual({
      field: "password",
      message: "That password is one of the most commonly used ones. Please choose something less guessable.",
    });
  });
});
