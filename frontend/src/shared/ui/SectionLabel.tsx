import type { ReactNode } from "react";

/** Small uppercase group heading -- was hand-duplicated verbatim in a
 * couple of pages; promoted here once a third consumer needed it. */
export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        fontFamily: "var(--arkive-font)",
        fontSize: "var(--text-xs)",
        fontWeight: 700,
        color: "var(--ink-600)",
        textTransform: "uppercase",
        letterSpacing: "0.04em",
      }}
    >
      {children}
    </div>
  );
}
