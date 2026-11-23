import { Link } from "react-router-dom";
import type { RequisitionDetail } from "../../../../../shared/api/pipeline";
import { colorFor } from "../../../../../shared/lib/identity";
import { jobStatusTone } from "../../../../../shared/lib/statusTags";
import { Card } from "../../../../../shared/ui/Card";
import { Tag } from "../../../../../shared/ui/Tag";
import { JOB_STATUS_LABEL, type JobEntry } from "./pipelineModel";

/** The selected opening's heading: title, department, status, head
 *  count, and links to its Workflow and Final Decision Board. */
export function JobSummaryCard({
  selected,
  deptColors,
  selectedOpen,
  selectedClosed,
  jobDetail,
}: {
  selected: JobEntry;
  deptColors: Map<string, string>;
  selectedOpen: number;
  selectedClosed: number;
  jobDetail: RequisitionDetail | null;
}) {
  return (
    <Card padding={20} elevation="md">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <h2 style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xl)", fontWeight: 700, color: "var(--ink-900)", margin: 0, letterSpacing: "-0.4px" }}>
              {selected.job.title}
            </h2>
            <Tag dotColor={colorFor(deptColors, selected.job.department)}>{selected.job.department}</Tag>
            <Tag tone={jobStatusTone(selected.job.status)} dot>
              {JOB_STATUS_LABEL[selected.job.status]}
            </Tag>
          </div>
          <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", margin: "8px 0 0" }}>
            {selectedOpen} still in play
            {selectedClosed > 0 && ` · ${selectedClosed} closed`}
            {jobDetail && ` · ${jobDetail.workflow_definition.length}-stage workflow`}
          </p>
        </div>
        {/* The two screens that belong to a job rather than to a
            candidate, reachable from the job rather than from a
            nav item that would then ask which job you meant. */}
        <div style={{ display: "flex", gap: 16, alignItems: "center", flexShrink: 0 }}>
          <Link
            to={`/hr/requisitions/${selected.job.id}/workflow`}
            style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--accent)", textDecoration: "none" }}
          >
            Workflow
          </Link>
          <Link
            to={`/hr/requisitions/${selected.job.id}/final-decision-board`}
            style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--accent)", textDecoration: "none" }}
          >
            Final Decision Board
          </Link>
        </div>
      </div>
    </Card>
  );
}
