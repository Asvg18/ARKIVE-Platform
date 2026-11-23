import type { AccessTokenPayload } from "./decodeJwt";

export function roleHomePath(role: AccessTokenPayload["role"]): string {
  switch (role) {
    case "applicant":
      return "/applicant";
    case "hr_admin":
      return "/hr";
    case "evaluator":
      return "/evaluator";
  }
}

/** Where to go after signing in or signing up: the `next` a link asked
 *  for (the job board's "browse all positions" sends ?next=/applicant/jobs),
 *  or the role's home.
 *
 *  Only a path inside the signed-in role's own portal is honoured. A
 *  `next` is whatever the link said, so an absolute URL or "//host" would
 *  make ARKIVE's own sign-in page a redirect to anywhere — and a path into
 *  another role's portal would only bounce off RequireRole anyway. */
export function afterSignInPath(role: AccessTokenPayload["role"], next: string | null): string {
  const home = roleHomePath(role);
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return home;
  if (next !== home && !next.startsWith(`${home}/`) && !next.startsWith(`${home}?`)) return home;
  return next;
}
