import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { roleHomePath } from "../model/roleHome";
import type { AccessTokenPayload } from "../model/decodeJwt";

/**
 * Gates a route tree by role. This is a CONVENIENCE, not the security
 * boundary — it just avoids flashing the wrong UI before a redirect. A
 * user could edit this out of their bundle and the route would render,
 * but every API call it makes still goes through the server-side
 * require_role() check, which is what actually protects the data.
 */
export function RequireRole({ allowed }: { allowed: AccessTokenPayload["role"][] }) {
  const { user } = useAuth();

  if (!user) return <Navigate to="/login" replace />;
  if (!allowed.includes(user.role)) return <Navigate to={roleHomePath(user.role)} replace />;

  return <Outlet />;
}
