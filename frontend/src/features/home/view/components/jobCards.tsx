/** The openings on the homepage: the department tabs, a job card and the
 *  job's detail dialog. */

import type { ReactNode } from "react";
import { initials } from "../../../../shared/lib/identity";
import { IdentityMark } from "../../../../shared/ui/IdentityMark";
import type { JobDetail, JobListItem } from "../../../../shared/api/public";
import { Card } from "../../../../shared/ui/Card";
import { Button } from "../../../../shared/ui/Button";
import { ArrowRightIcon, BriefcaseIcon, CheckIcon, ClockIcon, XIcon } from "../../../../shared/ui/icons";
import { daysUntil, deadlineLabel, timeAgo } from "../../model/jobDates";
import { StageRail } from "./landingSections";

export function DeptTab({
  active,
  onClick,
  color,
  count,
  children,
}: {
  active: boolean;
  onClick: () => void;
  color?: string;
  count?: number;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      className="ark-home__tab"
      style={color ? { ["--dept" as string]: color } : undefined}
      onClick={onClick}
    >
      {color && <span className="ark-home__tab-dot" aria-hidden="true" />}
      {children}
      {count != null && <span className="ark-home__tab-count">{count}</span>}
    </button>
  );
}

/**
 * One opening. The department's own colour marks it (the round badge)
 * so a returning applicant recognises the department
 * rather than re-reading it; the accent is kept for "act here". The
 * title is the one real control, stretched over the whole card, so the
 * card is a single click target without being a button full of blocks.
 */
export function JobCard({ job, color, onOpen }: { job: JobListItem; color: string; onOpen: () => void }) {
  const closingSoon = job.application_deadline != null && daysUntil(job.application_deadline) <= 14;

  return (
    <article className="ark-job">
      <div className="ark-job__top">
        <IdentityMark initials={initials(job.department)} color={color} size="lg" />
        <span className="ark-job__who">
          <span className="ark-job__dept">{job.department}</span>
          <span className="ark-job__posted">{timeAgo(job.created_at)}</span>
        </span>
        {closingSoon && <span className="ark-job__flag">Closing soon</span>}
      </div>

      <h3 className="ark-job__title">
        <button type="button" onClick={onOpen}>
          {job.title}
        </button>
      </h3>
      <StageRail count={job.stage_count} />

      {job.description && <p className="ark-job__desc">{job.description}</p>}

      <div className="ark-job__foot">
        {job.application_deadline ? (
          <span className="ark-job__deadline" data-soon={closingSoon || undefined}>
            <ClockIcon width={13} height={13} aria-hidden="true" />
            {deadlineLabel(job.application_deadline)}
          </span>
        ) : (
          <span className="ark-job__deadline">Open until filled</span>
        )}
        <span className="ark-job__cta" aria-hidden="true">
          View &amp; Apply
          <ArrowRightIcon width={13} height={13} />
        </span>
      </div>
    </article>
  );
}

export function JobDetailModal({
  job,
  applyError,
  applying,
  onApply,
  onClose,
}: {
  job: JobDetail;
  applyError: string | null;
  applying: boolean;
  onApply: () => void;
  onClose: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(17,17,19,0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
        zIndex: 50,
      }}
    >
      <div onClick={(e) => e.stopPropagation()} style={{ maxWidth: 540, width: "100%" }}>
        <Card padding={0} elevation="md" style={{ maxHeight: "85vh", overflowY: "auto" }}>
          <div style={{ padding: "28px 28px 0" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: "var(--radius)",
                  background: "var(--accent-gradient)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "white",
                  flexShrink: 0,
                }}
              >
                <BriefcaseIcon width={22} height={22} />
              </div>
              <button type="button" className="ark-home__modal-close" onClick={onClose} aria-label="Close">
                <XIcon width={20} height={20} />
              </button>
            </div>

            <div className="ark-home__eyebrow" style={{ marginTop: 14 }}>
              {job.department}
            </div>
            <h2 className="ark-home__modal-title">{job.title}</h2>
            <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-600)", marginTop: 6 }}>{timeAgo(job.created_at)}</div>

            {job.description && (
              <p style={{ fontSize: "var(--text-base)", color: "var(--ink-700)", marginTop: 16, lineHeight: 1.65 }}>{job.description}</p>
            )}

            <RequirementList label="Qualifications" text={job.qualifications} />
            <RequirementList label="Requirements" text={job.requirements} />
            {(job.additional_sections ?? []).map((section, i) => (
              <RequirementList key={i} label={section.title.trim() || "More details"} text={section.content} />
            ))}
          </div>

          <div style={{ padding: "20px 28px 28px", marginTop: 20 }}>
            {job.application_deadline && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  fontSize: "var(--text-sm)",
                  fontWeight: 600,
                  color: "var(--ink-700)",
                  background: "var(--surface-bg-alt)",
                  borderRadius: "var(--radius)",
                  padding: "8px 12px",
                  marginBottom: 16,
                }}
              >
                <ClockIcon width={14} height={14} />
                {deadlineLabel(job.application_deadline)}
              </div>
            )}

            {applyError && <p style={{ color: "var(--warning-text)", fontSize: "var(--text-sm)", marginBottom: 12 }}>{applyError}</p>}

            <Button variant="primary" onClick={onApply} disabled={applying} style={{ width: "100%" }}>
              {applying ? "Submitting..." : "Apply Now"}
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}

function RequirementList({ label, text }: { label: string; text: string | null }) {
  const items = (text ?? "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (items.length === 0) return null;

  return (
    <>
      <div
        style={{
          fontSize: "var(--text-xs)",
          fontWeight: 700,
          color: "var(--ink-700)",
          textTransform: "uppercase",
          letterSpacing: "0.04em",
          marginTop: 20,
        }}
      >
        {label}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
        {items.map((line, i) => (
          <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
            <CheckIcon width={14} height={14} style={{ color: "var(--accent)", marginTop: 3, flexShrink: 0 }} />
            <span style={{ fontSize: "var(--text-base)", color: "var(--ink-900)", lineHeight: 1.5 }}>{line}</span>
          </div>
        ))}
      </div>
    </>
  );
}
