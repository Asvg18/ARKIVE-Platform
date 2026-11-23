/**
 * A list of agent-written findings (strengths, gaps, areas of concern),
 * laid out as prose.
 */

import { useState } from "react";


/** Findings are full sentences, so each wraps as prose with a coloured
 * rule carrying the good or bad signal; a nowrap pill would push its
 * column past the viewport. `limit` shows the first few and folds the
 * rest behind "Show N more", for screens read many times over (the
 * Candidate Profile), where a dozen findings would push everything
 * beneath them away. */
export function ReasonList({
  title,
  items,
  tone,
  limit,
}: {
  title: string;
  items: string[];
  tone: "success" | "warning";
  limit?: number;
}) {
  const [showAll, setShowAll] = useState(false);
  const color = tone === "success" ? "var(--success-text)" : "var(--warning-text)";
  const folded = limit != null && !showAll && items.length > limit + 1;
  const shown = folded ? items.slice(0, limit) : items;
  return (
    <div>
      <div
        style={{
          fontFamily: "var(--arkive-font)",
          fontSize: "var(--text-2xs)",
          fontWeight: 700,
          color: "var(--ink-600)",
          textTransform: "uppercase",
          letterSpacing: "0.04em",
          marginBottom: 8,
        }}
      >
        {title}
      </div>
      <ul
        style={{
          margin: 0,
          padding: 0,
          listStyle: "none",
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        {shown.map((item) => (
          <li
            key={item}
            style={{
              fontFamily: "var(--arkive-font)",
              fontSize: "var(--text-sm)",
              lineHeight: 1.6,
              color: "var(--ink-900)",
              paddingLeft: 14,
              borderLeft: `2px solid ${color}`,
              // Belt and braces against the defect this component exists
              // to fix: a single unbroken token (a long URL in a gap, a
              // pasted identifier) must break rather than widen the page.
              minWidth: 0,
              overflowWrap: "anywhere",
            }}
          >
            {item}
          </li>
        ))}
      </ul>
      {limit != null && items.length > limit + 1 && (
        <button type="button" className="ark-more" aria-expanded={showAll} onClick={() => setShowAll((v) => !v)}>
          {showAll ? "Show fewer" : `Show ${items.length - limit} more`}
        </button>
      )}
    </div>
  );
}
