import { Link } from "react-router-dom";
import type { ApplicationDetail } from "../../../../shared/api/applicant";
import { getApplicantSkillMatchPayload } from "../../../../shared/api/skillMatch";
import { Button } from "../../../../shared/ui/Button";
import { AlertIcon, ArrowRightIcon } from "../../../../shared/ui/icons";

/**
 * Shown instead of the normal stage screen when application.status is
 * "flagged": the Skill Matching Agent (backend/app/services/
 * skill_matching/) scored the candidate below the job's fit threshold.
 * It is not a rejection: the DFA is held at skill_matching until HR
 * reviews it (POST /hr/applications/{id}/resolve-flag) and either rejects
 * or lets the candidate continue.
 *
 * The score, strengths and gaps behind the flag stay HR-only (a critical
 * AI breakdown of your own shortcomings discourages whatever the
 * outcome), and the backend never sends them to the applicant (see
 * _redact_skill_matching_payload). This screen gets only the constructive
 * half: a plain explanation, and the suggested alternative openings from
 * the same ranking pass, a block that hides itself when there are none.
 */
export function FlaggedReviewScreen({ application }: { application: ApplicationDetail }) {
  const skillMatch = getApplicantSkillMatchPayload(application.stage_instances);
  const suggestions = skillMatch?.suggested_requisitions ?? [];

  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: "50%",
            background: "var(--warning-bg)",
            color: "var(--warning-text)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <AlertIcon width={18} height={18} />
        </div>
        <div>
          <h2 style={heading}>Application Under Review</h2>
          <p style={subtext}>
            Your application for {application.job_title} needs a closer look before moving forward. This isn't a
            rejection. An HR administrator will personally review your resume before any final decision is made.
          </p>
        </div>
      </div>

      {suggestions.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <h3 style={{ ...heading, fontSize: "var(--text-lg)" }}>Other Openings You Might Like</h3>
          <p style={subtext}>While that's under review, here are other currently open positions worth a look.</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 14 }}>
            {suggestions.map((s) => (
              <div
                key={s.requisition_id}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  border: "1px solid var(--surface-border)",
                  borderRadius: "var(--radius)",
                  padding: "12px 16px",
                }}
              >
                <div>
                  <div style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", fontWeight: 700, color: "var(--ink-900)" }}>
                    {s.title}
                  </div>
                  <div style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xs)", color: "var(--ink-600)" }}>{s.department}</div>
                </div>
                <ArrowRightIcon width={16} height={16} style={{ color: "var(--ink-400)", flexShrink: 0 }} />
              </div>
            ))}
          </div>
          <Link to="/applicant/jobs" style={{ textDecoration: "none" }}>
            <Button variant="primary" style={{ marginTop: 16 }}>
              Find Jobs
            </Button>
          </Link>
        </div>
      )}
    </div>
  );
}

const heading: React.CSSProperties = { fontFamily: "var(--arkive-font)", fontSize: "var(--text-xl)", fontWeight: 700, color: "var(--ink-900)", margin: 0 };
const subtext: React.CSSProperties = { fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", marginTop: 6, lineHeight: 1.6 };
