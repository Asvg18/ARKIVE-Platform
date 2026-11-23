import type { ApplicationDetail } from "../../../../shared/api/applicant";
import { stageLabel } from "../../../../shared/lib/stageLabels";
import { ClockIcon } from "../../../../shared/ui/icons";

/** Read-only for final_decision — HR-driven, not an applicant action
 * (sprint handoff §5c).
 * Shortlisting reuses this too (see ApplicationStagePage) with its own
 * heading — same "nothing for you to do here" fact, just not literally
 * *final* consideration this early in the pipeline. */
export function FinalSelectionScreen({
  application,
  heading = "Under Final Consideration",
}: {
  application: ApplicationDetail;
  heading?: string;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", padding: "24px 0" }}>
      <div
        style={{
          width: 56,
          height: 56,
          borderRadius: "50%",
          background: "var(--accent-bg)",
          color: "var(--accent)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          marginBottom: 16,
        }}
      >
        <ClockIcon width={26} height={26} />
      </div>
      <h2 style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xl)", fontWeight: 700, color: "var(--ink-900)", margin: 0 }}>
        {heading}
      </h2>
      <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", marginTop: 8, maxWidth: 420 }}>
        Your application for <strong style={{ color: "var(--ink-900)" }}>{application.job_title}</strong> is currently on{" "}
        {stageLabel(application.current_stage)}. No action is needed from you right now. HR is completing this
        step. You'll see your status update here once it's done.
      </p>
    </div>
  );
}
