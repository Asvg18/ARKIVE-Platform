import type { NavigateFunction } from "react-router-dom";
import type { ApplicationListItem, StageType } from "../../../../../shared/api/pipeline";
import { stageLabel, STATUS_LABELS } from "../../../../../shared/lib/stageLabels";
import { applicationStatusTone } from "../../../../../shared/lib/statusTags";
import { Avatar } from "../../../../../shared/ui/Avatar";
import { Button } from "../../../../../shared/ui/Button";
import { Card } from "../../../../../shared/ui/Card";
import { ArrowRightIcon } from "../../../../../shared/ui/icons";
import { Tag } from "../../../../../shared/ui/Tag";
import { ellipsis, type RankedRow } from "./pipelineModel";

/** The List view: one opening's candidates ranked by match score, each
 *  row opening the profile, with an Advance button while active. */
export function CandidateList({
  rankedListRows,
  navigate,
  labelFor,
  handleAdvance,
  movingId,
  rowError,
}: {
  rankedListRows: RankedRow[];
  navigate: NavigateFunction;
  labelFor: (stage: StageType | null) => string;
  handleAdvance: (application: ApplicationListItem) => void;
  movingId: number | null;
  rowError: Record<number, string>;
}) {
  return (
    <Card padding={0} elevation="md">
      <div style={{ overflowX: "auto" }}>
        <table className="ark-table ark-table--rows" style={{ minWidth: 720, tableLayout: "fixed" }}>
          {/* Rank and Match % belong here though the board card leaves
              them out: this list is one job's candidates, the only
              comparison a rank means anything within. */}
          <colgroup>
            <col style={{ width: "6%" }} />
            <col style={{ width: "22%" }} />
            <col style={{ width: "20%" }} />
            {/* 14%, not 10%. "MATCH %" measures ~66px at
                13px/700/0.04em, and 10% left only ~40px of
                text width at this table's 720px minimum once
                the cell's own 32px of padding came off -- so
                it broke to "MATCH" over "%". Borrowed from
                Candidate and Stage, which truncate cleanly. */}
            <col style={{ width: "14%" }} />
            {/* Status: room for its fixed-width tags ("Flagged for
                Review") at 720px, taken from Candidate and Stage,
                which truncate cleanly. */}
            <col style={{ width: "22%" }} />
            <col style={{ width: "16%" }} />
          </colgroup>
          <thead>
            <tr>
              <th style={{ textAlign: "right" }}>Rank</th>
              <th>Candidate</th>
              <th>Stage</th>
              <th style={{ textAlign: "right" }}>Match %</th>
              <th className="ark-status-cell ark-status-cell--wide">Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rankedListRows.map(({ application, rank }) => {
              const canAdvance = application.next_stage && application.status === "active";
              return (
                <tr
                  key={application.id}
                  tabIndex={0}
                  aria-label={`View ${application.applicant_name}'s profile for ${application.job_title}`}
                  onClick={() => navigate(`/hr/applications/${application.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") navigate(`/hr/applications/${application.id}`);
                  }}
                >
                  <td
                    className="ark-num"
                    style={{
                      textAlign: "right",
                      fontWeight: 650,
                      color: rank != null ? "var(--ink-900)" : "var(--ink-300)",
                    }}
                  >
                    {rank ?? "–"}
                  </td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                      <Avatar name={application.applicant_name} size={26} src={application.applicant_avatar_url} />
                      <span
                        title={application.applicant_name}
                        style={{ fontWeight: 600, color: "var(--ink-900)", flex: 1, minWidth: 0, ...ellipsis }}
                      >
                        {application.applicant_name}
                      </span>
                    </div>
                  </td>
                  {/* Where they are and where they go next, in
                      one cell — the job column this replaced
                      said nothing you could not read off the
                      heading above the table. */}
                  <td>
                    <div
                      title={application.current_stage_label ?? undefined}
                      style={{ fontWeight: 600, color: "var(--ink-900)", ...ellipsis }}
                    >
                      {application.current_stage_label ?? stageLabel(application.current_stage)}
                    </div>
                    <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-400)", marginTop: 3, ...ellipsis }}>
                      {application.next_stage
                        ? `Next: ${labelFor(application.next_stage)}`
                        : application.status === "active"
                        ? "Final stage of this workflow"
                        : "–"}
                    </div>
                  </td>
                  <td
                    className="ark-num"
                    style={{
                      textAlign: "right",
                      color: application.match_score != null ? "var(--ink-900)" : "var(--ink-300)",
                    }}
                  >
                    {application.match_score != null ? `${application.match_score}%` : "–"}
                  </td>
                  <td className="ark-status-cell ark-status-cell--wide">
                    <Tag tone={applicationStatusTone(application.status)} dot>
                      {STATUS_LABELS[application.status] ?? application.status}
                    </Tag>
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", alignItems: "center" }}>
                      <div style={{ width: 96, display: "flex", justifyContent: "flex-end" }}>
                        {canAdvance && (
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleAdvance(application);
                            }}
                            disabled={movingId === application.id}
                            style={{ width: "100%" }}
                          >
                            {movingId === application.id ? "Advancing..." : "Advance"}
                          </Button>
                        )}
                      </div>
                      <ArrowRightIcon width={16} height={16} className="ark-row-go" style={{ color: "var(--ink-400)", flexShrink: 0 }} />
                    </div>
                    {rowError[application.id] && (
                      <div style={{ color: "crimson", fontSize: "0.8em", marginTop: 4, textAlign: "right" }}>
                        {rowError[application.id]}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
