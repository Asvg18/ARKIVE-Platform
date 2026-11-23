/** Display helpers the Candidate Profile's tabs share. Not components, so
 *  they live apart from atoms.tsx and fast refresh keeps working there. */

import type React from "react";

export const scheduleInputStyle: React.CSSProperties = {
  padding: "8px 10px",
  borderRadius: "var(--radius)",
  border: "1px solid var(--surface-border)",
  background: "var(--surface)",
  fontFamily: "var(--arkive-font)",
  fontSize: "var(--text-sm)",
  color: "var(--ink-900)",
};

export function capitalize(s: string): string {
  return s
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
