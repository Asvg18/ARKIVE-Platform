import { useEffect, useState, type ReactNode } from "react";
import { useAuth } from "../../../../auth/controller/AuthContext";
import { ApiError, apiFetch } from "../../../../../shared/api/client";
import type { ApplicationDetail } from "../../../../../shared/api/applicant";
import type { JobDetail, JobListItem } from "../../../../../shared/api/public";
import { initials } from "../../../../../shared/lib/identity";
import { IdentityMark } from "../../../../../shared/ui/IdentityMark";
import { Alert } from "../../../../../shared/ui/Alert";
import { Button } from "../../../../../shared/ui/Button";
import { BriefcaseIcon, CheckIcon, ClockIcon, LayersIcon } from "../../../../../shared/ui/icons";
import { Tag } from "../../../../../shared/ui/Tag";
import { deadlineLabel, isSoon, lines, timeAgo } from "./jobListModel";

/** The chosen job, in full: the public record plus this applicant's own
 *  standing with it. */
export function JobPanel({
  job,
  color,
  application,
  onApplied,
  onOpenApplication,
}: {
  job: JobListItem;
  color: string;
  application: ApplicationDetail | null;
  onApplied: (created: ApplicationDetail) => void;
  onOpenApplication: (id: number) => void;
}) {
  const { token } = useAuth();
  const [detail, setDetail] = useState<JobDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<JobDetail>(`/public/jobs/${job.id}`)
      .then(setDetail)
      .catch((err) => setDetailError(err instanceof ApiError ? err.message : "Couldn't load this position."));
  }, [job.id]);

  async function apply() {
    setApplying(true);
    setApplyError(null);
    try {
      const created = await apiFetch<ApplicationDetail>("/applications", {
        method: "POST",
        token,
        body: { requisition_id: job.id },
      });
      onApplied(created);
    } catch (err) {
      setApplyError(err instanceof ApiError ? err.message : "Couldn't submit your application. Try again.");
    } finally {
      setApplying(false);
    }
  }

  const stages = detail?.stage_labels?.length ? detail.stage_labels : [];
  const qualifications = lines(detail?.qualifications ?? job.qualifications);
  const requirements = lines(detail?.requirements ?? job.requirements);
  const otherSections = (detail?.additional_sections ?? job.additional_sections ?? []).filter(
    (section) => section.title.trim() || section.content.trim(),
  );

  return (
    <article className="ark-jobpanel" aria-label={job.title}>
      <header className="ark-jobpanel__head">
        <IdentityMark initials={initials(job.department)} color={color} size="xl" />
        <div className="ark-jobpanel__heading">
          <h2>{job.title}</h2>
          <p>
            {job.department} · {timeAgo(job.created_at)}
          </p>
        </div>
        <div className="ark-jobpanel__actions">
          {application ? (
            <>
              <Tag tone="green">
                <CheckIcon width={12} height={12} aria-hidden="true" />
                Applied
              </Tag>
              <Button variant="secondary" onClick={() => onOpenApplication(application.id)}>
                View My Application
              </Button>
            </>
          ) : (
            <Button variant="primary" onClick={apply} disabled={applying}>
              {applying ? "Applying…" : "Apply Now"}
            </Button>
          )}
        </div>
      </header>

      <div className="ark-jobpanel__facts">
        <Fact icon={<ClockIcon width={15} height={15} />} label="Deadline" soon={isSoon(job.application_deadline)}>
          {deadlineLabel(job.application_deadline)}
        </Fact>
        <Fact icon={<LayersIcon width={15} height={15} />} label="Hiring process">
          {job.stage_count} stages
        </Fact>
        <Fact icon={<BriefcaseIcon width={15} height={15} />} label="Department">
          {job.department}
        </Fact>
      </div>

      {applyError && <Alert tone="danger" title={applyError} />}
      {detailError && <Alert tone="warning" title={detailError} />}

      {(detail?.description ?? job.description) && (
        <section className="ark-jobpanel__section">
          <h3>About the role</h3>
          <p>{detail?.description ?? job.description}</p>
        </section>
      )}

      {qualifications.length > 0 && <Checklist title="Qualifications" items={qualifications} />}
      {requirements.length > 0 && <Checklist title="Requirements" items={requirements} />}
      {/* The rest of the posting, under the job description's own
          headings: salary, benefits, documents to submit... */}
      {otherSections.map((section, i) => (
        <section key={i} className="ark-jobpanel__section">
          {section.title.trim() && <h3>{section.title.trim()}</h3>}
          {section.content.trim() && <p className="ark-jobpanel__text">{section.content.trim()}</p>}
        </section>
      ))}

      {stages.length > 0 && (
        <section className="ark-jobpanel__section">
          <h3>How hiring works for this role</h3>
          <ol className="ark-jobpanel__stages">
            {stages.map((label, i) => (
              <li key={`${label}-${i}`}>
                <span className="ark-jobpanel__stage-n" aria-hidden="true">
                  {i + 1}
                </span>
                <span className="ark-jobpanel__stage-label">{label}</span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </article>
  );
}

function Fact({ icon, label, soon = false, children }: { icon: ReactNode; label: string; soon?: boolean; children: ReactNode }) {
  return (
    <div className="ark-jobpanel__fact" data-soon={soon || undefined}>
      <span className="ark-jobpanel__fact-icon" aria-hidden="true">
        {icon}
      </span>
      <span className="ark-jobpanel__fact-text">
        <span className="ark-jobpanel__fact-label">{label}</span>
        <span className="ark-jobpanel__fact-value">{children}</span>
      </span>
    </div>
  );
}

function Checklist({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="ark-jobpanel__section">
      <h3>{title}</h3>
      <ul className="ark-jobpanel__checks">
        {items.map((item, i) => (
          <li key={i}>
            <CheckIcon width={13} height={13} aria-hidden="true" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
