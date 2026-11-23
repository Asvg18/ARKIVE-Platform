import type { Dispatch, RefObject, SetStateAction } from "react";
import { Link } from "react-router-dom";
import type { RequisitionListItem } from "../../../../../shared/api/pipeline";
import { colorFor, initials } from "../../../../../shared/lib/identity";
import { Card } from "../../../../../shared/ui/Card";
import { IdentityMark } from "../../../../../shared/ui/IdentityMark";
import { SearchIcon } from "../../../../../shared/ui/icons";
import { isOpen, type RailSection } from "./pipelineModel";

/** The left rail: the search box and every opening, sectioned by status,
 *  each with its count of candidates still in play (or matching the
 *  search). */
export function OpeningsRail({
  search,
  setSearch,
  query,
  railRef,
  railSections,
  jobs,
  selectedJobId,
  selectJob,
  deptColors,
}: {
  search: string;
  setSearch: Dispatch<SetStateAction<string>>;
  query: string;
  railRef: RefObject<HTMLDivElement | null>;
  railSections: RailSection[];
  jobs: RequisitionListItem[];
  selectedJobId: number | null;
  selectJob: (id: number) => void;
  deptColors: Map<string, string>;
}) {
  return (
    <aside style={{ width: 284, flexShrink: 0, position: "sticky", top: 16 }}>
      <div style={{ position: "relative", marginBottom: 12 }}>
        <SearchIcon
          width={16}
          height={16}
          style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--ink-400)" }}
        />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search candidates or jobs..."
          aria-label="Search candidates or jobs"
          style={{
            width: "100%",
            padding: "9px 12px 9px 34px",
            borderRadius: "var(--radius-sm)",
            fontSize: "var(--text-sm)",
          }}
        />
      </div>

      {/* Its own scroll, so a long list of openings never scrolls the
          pipeline beside it out of view. */}
      <Card padding={0} elevation="sm" style={{ overflow: "hidden" }}>
        {/* The scroll lives on this inner box rather than on the
            Card, so the card's rounded corners still clip it, and
            `position: relative` makes it the box the rows' offsetTop
            is measured against.

            The 300px is this page's own header — the heading, its
            summary line and the margins above the rail. Subtracting
            it is what keeps the rail from hanging past the bottom of
            the window before you have scrolled anything, which is
            the state in which a row below the fold looks like a row
            that isn't there. */}
        <div
          ref={railRef}
          className="pipeline-rail ark-row-list"
          style={{
            position: "relative",
            maxHeight: "max(260px, calc(100vh - 300px))",
            overflowY: "auto",
            padding: "var(--space-1-5)",
          }}
        >
        {railSections.map((section) => (
          <div key={section.status}>
            <div
              className="ark-meta"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--space-2)",
                padding: "14px 10px 8px",
              }}
            >
              <span>{section.label}</span>
              <span className="ark-num" style={{ color: "var(--ink-300)" }}>{section.entries.length}</span>
              {/* A hairline that runs out to the edge, so the eye
                  reads the group as a band rather than as a label
                  floating above unrelated rows. */}
              <span style={{ flex: 1, height: 1, background: "var(--hairline)" }} />
            </div>
            {section.entries.map((entry) => {
              const open = entry.all.filter(isOpen).length;
              const active = entry.job.id === selectedJobId;
              return (
                <button
                  key={entry.job.id}
                  data-job-id={entry.job.id}
                  onClick={() => selectJob(entry.job.id)}
                  aria-current={active ? "true" : undefined}
                  title={`${entry.job.title} · ${entry.job.department}`}
                  className="ark-row ark-row--marked"
                  style={{ paddingLeft: "var(--space-2-5)" }}
                >
                  {/* Identity, not status. Every open job used to carry
                      the same green bar, which is colour spending its
                      budget and buying nothing — fifteen of fifteen
                      green says exactly what no colour says. Tinting by
                      department instead makes a row findable without
                      being read, and repeats across screens so it is
                      learnable. See lib/identity.ts. */}
                  <IdentityMark initials={initials(entry.job.title)} color={colorFor(deptColors, entry.job.department)} />

                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span
                      className="ark-truncate"
                      style={{
                        display: "block",
                        fontSize: "var(--text-sm)",
                        fontWeight: 650,
                        letterSpacing: "var(--track-snug)",
                        color: "var(--ink-900)",
                        lineHeight: 1.35,
                      }}
                    >
                      {entry.job.title}
                    </span>
                    <span
                      className="ark-truncate"
                      style={{
                        display: "block",
                        fontSize: "var(--text-xs)",
                        color: "var(--ink-400)",
                        marginTop: 1,
                        lineHeight: 1.35,
                      }}
                    >
                      {entry.job.department}
                    </span>
                  </span>

                  {/* The count, and only the count. Every row used to
                      repeat the word ACTIVE beneath its number —
                      fifteen times down a 15-row list, which is
                      furniture rather than information. The column is
                      self-evident once you have read it once, so the
                      label moved to the tooltip and a zero recedes to
                      a dash instead of shouting a bright 0. */}
                  <span
                    className="ark-row__count"
                    title={query ? "candidates matching your search" : "candidates still in play"}
                    data-zero={(query ? entry.visible.length : open) === 0 || undefined}
                    data-search={query ? true : undefined}
                  >
                    {(query ? entry.visible.length : open) || "–"}
                  </span>
                </button>
              );
            })}
          </div>
        ))}

        {railSections.length === 0 && (
          <div style={{ padding: 20, fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", lineHeight: 1.6 }}>
            {jobs.length === 0 ? (
              <>
                No job openings yet.{" "}
                <Link to="/hr/requisitions/new" style={{ color: "var(--accent)", fontWeight: 600 }}>
                  Create one
                </Link>{" "}
                to start a pipeline.
              </>
            ) : (
              <>
                Nothing matches "{search.trim()}".{" "}
                <button
                  onClick={() => setSearch("")}
                  style={{ border: "none", background: "none", padding: 0, color: "var(--accent)", fontWeight: 600, cursor: "pointer", font: "inherit" }}
                >
                  Clear the search
                </button>{" "}
                to see every opening.
              </>
            )}
          </div>
        )}
        </div>
      </Card>
    </aside>
  );
}
