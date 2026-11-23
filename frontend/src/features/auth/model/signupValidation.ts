/** The sign-up form's rules and the sentences it shows when one is
 * broken. Kept out of the page so each rule can be tested on its own,
 * and so the messages live in one place rather than scattered through
 * JSX. The server enforces the same limits (schemas/auth.py); these run
 * first so a person hears about a mistake at the field, not after a
 * round trip. Accepting an invitation creates an account too, and uses
 * the same rules (INVITE_FIELDS below). */

export type SignupField = "firstName" | "lastName" | "email" | "password" | "confirmPassword";

export type SignupValues = Record<SignupField, string>;

export type SignupErrors = Partial<Record<SignupField, string>>;

/** Order the fields appear in, so a failed submit can focus the first
 * one that needs fixing. */
export const SIGNUP_FIELDS: SignupField[] = ["firstName", "lastName", "email", "password", "confirmPassword"];

/** What an invited HR admin or evaluator fills in: the sign-up form less
 * the email, which the invitation already fixed. The email still goes
 * in the values, because the password rule reads it. */
export const INVITE_FIELDS: SignupField[] = ["firstName", "lastName", "password", "confirmPassword"];

const NAME_MAX = 100;
const PASSWORD_MIN = 8;
// bcrypt's ceiling is 72 bytes; the server words it in characters too.
const PASSWORD_MAX = 72;

// Any script's letters and their accents (Niño, Peña, Zoë), with the
// spaces, hyphens, apostrophes and periods real names carry ("Ma.
// Cristina", "Dela Cruz-Santos", "O'Brien"). Must start with a letter.
const NAME_PATTERN = /^\p{L}[\p{L}\p{M}' .\-’]*$/u;

// Deliberately loose — one @, something either side, a dot in the
// domain. The server's check is the strict one; this only catches the
// slips a person would want pointed out before sending.
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function checkName(value: string, label: "First name" | "Last name"): string | undefined {
  const v = value.trim();
  if (!v) return `Enter your ${label.toLowerCase()}.`;
  if (v.length > NAME_MAX) return `${label} must be ${NAME_MAX} characters or fewer.`;
  // Short enough for the half-width name column. Hyphens, apostrophes
  // and periods are symbols too, but nobody reads a name rule as
  // forbidding the ones in their own name.
  if (!NAME_PATTERN.test(v)) return `${label} can't contain numbers or symbols.`;
  return undefined;
}

export function validateSignupField(field: SignupField, values: SignupValues): string | undefined {
  switch (field) {
    case "firstName":
      return checkName(values.firstName, "First name");
    case "lastName":
      return checkName(values.lastName, "Last name");
    case "email": {
      const v = values.email.trim();
      if (!v) return "Enter your email address.";
      if (!EMAIL_PATTERN.test(v)) return "Enter a valid email address, like name@example.com.";
      return undefined;
    }
    case "password": {
      const v = values.password;
      if (!v) return "Create a password.";
      if (v.length < PASSWORD_MIN) return `Password must be at least ${PASSWORD_MIN} characters.`;
      if (v.length > PASSWORD_MAX) return `Password must be ${PASSWORD_MAX} characters or fewer.`;
      if (v.trim().toLowerCase() === values.email.trim().toLowerCase()) {
        return "Password can't be the same as your email address.";
      }
      return undefined;
    }
    case "confirmPassword": {
      if (!values.confirmPassword) return "Confirm your password.";
      // Checked here because the server never sees this field — it only
      // receives one password, so a typo would be silently accepted and
      // lock the person out of the account they just made.
      if (values.confirmPassword !== values.password) return "Passwords don't match.";
      return undefined;
    }
  }
}

export function validateSignup(values: SignupValues, fields: SignupField[] = SIGNUP_FIELDS): SignupErrors {
  const errors: SignupErrors = {};
  for (const field of fields) {
    const message = validateSignupField(field, values);
    if (message) errors[field] = message;
  }
  return errors;
}

/** One name for the account, the way the rest of the system stores it:
 * first and last joined, runs of spaces closed up. */
export function joinFullName(firstName: string, lastName: string): string {
  return `${firstName} ${lastName}`.trim().replace(/\s+/g, " ");
}

/**
 * What a rejected sign-up means for the form: which field it belongs to
 * and what to say, or a message for the form as a whole.
 *
 * The server's 422 is a list of {loc, msg}; `loc` names the field
 * (["body", "password"]). Its password messages are already written for
 * a person (too common, too long) and pass through; the email one is
 * the validator library's technical phrasing and is replaced.
 */
export function signupErrorFromServer(
  status: number,
  detail: unknown,
  message: string
): { field?: SignupField; message: string; kind?: "duplicate-email" } {
  if (status === 409) {
    return { field: "email", message: "An account with this email address already exists.", kind: "duplicate-email" };
  }

  if (status === 422 && Array.isArray(detail)) {
    for (const item of detail) {
      if (!item || typeof item !== "object") continue;
      const loc = (item as { loc?: unknown }).loc;
      const msg = (item as { msg?: unknown }).msg;
      const key = Array.isArray(loc) ? loc[loc.length - 1] : undefined;
      if (key === "email") return { field: "email", message: "Enter a valid email address, like name@example.com." };
      if (key === "password" && typeof msg === "string") {
        const text = msg.replace(/^Value error,\s*/i, "");
        // Pydantic's own min-length wording, should the rules above ever
        // drift from the server's.
        if (/at least \d+ characters/i.test(text)) {
          return { field: "password", message: `Password must be at least ${PASSWORD_MIN} characters.` };
        }
        return { field: "password", message: text };
      }
      if (key === "full_name") return { field: "firstName", message: "Check your first and last name." };
    }
  }

  if (status === 0) return { message }; // timed out or unreachable — apiFetch's own sentence
  if (status === 429) return { message }; // the server's sentence names the wait
  if (status >= 500) return { message: "Something went wrong on our side. Please try again in a moment." };
  return { message: message || "We couldn't create your account. Please try again." };
}

/**
 * The same for accepting an invitation. A 404 or 409 is about the
 * invitation, not anything typed into the form, so it goes over the
 * button -- read as sign-up reads it, a 409 would land on an email field
 * this form doesn't have, and the person would see nothing at all.
 *
 * The page only shows the form for an invitation that was open when it
 * loaded, and invitations are never deleted, so a 404 here means a
 * resend replaced the link since. A 409's own sentence already says
 * which (used, revoked, expired, or the address has an account now).
 */
export function inviteErrorFromServer(
  status: number,
  detail: unknown,
  message: string
): { field?: SignupField; message: string } {
  if (status === 404) return { message: "This invitation link was replaced by a newer one. Use the most recent link you were sent." };
  if (status === 409) return { message: message || "This invitation can no longer be used." };
  return signupErrorFromServer(status, detail, message);
}
