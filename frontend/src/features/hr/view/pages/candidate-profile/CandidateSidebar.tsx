/**
 * The Candidate Profile's left-hand column: the candidate card, the
 * verdict and contact details, held in view on every tab.
 */

import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { CandidateProfile, HeadlineSignal, RequisitionDetail } from "../../../../../shared/api/pipeline";
import { isExamStage, stageLabel, STATUS_LABELS } from "../../../../../shared/lib/stageLabels";
import { applicationStatusTone } from "../../../../../shared/lib/statusTags";
import { Avatar } from "../../../../../shared/ui/Avatar";
import { Button } from "../../../../../shared/ui/Button";
import { ArrowRightIcon, LinkIcon, MailIcon, MapPinIcon, PhoneIcon } from "../../../../../shared/ui/icons";
import { SynthesisVerdict } from "../../components/synthesis/SynthesisVerdict";

interface CandidateSidebarProps {
  profile: CandidateProfile;
  /** The job, for its workflow (the stage bar) and department. Null until
   *  it loads; the card simply shows less until then. */
  job: RequisitionDetail | null;
  pipelineHref: string;
  updating: boolean;
  advancing: boolean;
  advanceError: string | null;
  actionError: string | null;
  onAdvance: () => void;
  onDecide: (mode: "hire" | "reject") => void;
  onResolveFlag: (decision: "continue" | "reject") => void;
  onReopen: () => void;
  onOpenPackage: () => void;
  /** Takes HR from one of the verdict's facts to the tab that argues it. */
  onOpenSignal: (key: HeadlineSignal["key"]) => void;
}

/** The essentials, held in view while the record on the right scrolls:
 * the candidate card (who, for which job, where they stand in its
 * workflow, and the next move: advance, hire or reject), the verdict, and
 * contact details as read from their resume. Arranged after a reference
 * HR supplied (identity and stage top left, actions beneath, contact at
 * the foot); a section with nothing to show is left out, not padded. */
export function CandidateSidebar(props: CandidateSidebarProps) {
  const { profile, job, pipelineHref } = props;
  const stageName = profile.current_stage_label ?? stageLabel(profile.current_stage);

  return (
    <aside className="ark-profile__side" aria-label="Candidate summary">
      <section className="ark-panel">
        <div className="ark-panel__section">
          <div className="ark-person">
            <span aria-hidden="true" style={{ display: "inline-flex" }}>
              <Avatar name={profile.applicant_name} size={52} src={profile.applicant_avatar_url} />
            </span>
            <div style={{ minWidth: 0 }}>
              <h2 className="ark-person__name">{profile.applicant_name}</h2>
              {/* The job is a link, so "who else is up for this role" is
                  one click from any candidate. */}
              <Link to={pipelineHref} className="ark-link-quiet ark-person__job">
                {profile.job_title}
              </Link>
              {job?.department && <p className="ark-person__meta">{job.department}</p>}
            </div>
          </div>
        </div>

        <div className="ark-panel__section">
          <StageBar profile={profile} job={job} stageName={stageName} />
        </div>

        <div className="ark-panel__section" data-tone={profile.status === "flagged" ? "warning" : undefined}>
          <NextMove {...props} stageName={stageName} />
        </div>

        {(profile.status === "active" || profile.status === "flagged") && (
          <EndApplication
            flagged={profile.status === "flagged"}
            updating={props.updating}
            onReject={() => (profile.status === "flagged" ? props.onResolveFlag("reject") : props.onDecide("reject"))}
          />
        )}
      </section>

      <SynthesisVerdict synthesis={profile.synthesis} onOpenSignal={props.onOpenSignal} />

      <Contact profile={profile} />
    </aside>
  );
}

/** One segment per stage of this job's own workflow, the current one
 *  named. Before the job has loaded there is nothing to count against, so
 *  it says only where they are. */
function StageBar({
  profile,
  job,
  stageName,
}: {
  profile: CandidateProfile;
  job: RequisitionDetail | null;
  stageName: string;
}) {
  const stages = job?.workflow_definition ?? [];
  const index = profile.current_stage ? stages.indexOf(profile.current_stage) : -1;
  // A hire has finished the workflow whatever stage it was recorded at.
  const finished = profile.status === "hired";

  return (
    <div className="ark-stage">
      <div className="ark-stage__head">
        <span className="ark-eyebrow-quiet" style={{ margin: 0 }}>
          Stage
        </span>
        {index >= 0 && (
          <span className="ark-stage__count">
            {index + 1} of {stages.length}
          </span>
        )}
      </div>
      <div className="ark-stage__now" style={{ marginBottom: stages.length > 0 ? 10 : 0 }}>
        <span className="ark-truncate">{stageName}</span>
      </div>
      {index >= 0 && (
        <div className="ark-stage__bar" aria-hidden="true">
          {stages.map((stage, i) => (
            <span
              key={stage}
              data-state={finished || i < index ? "done" : i === index ? "current" : undefined}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** Reject, kept apart from the main action in its own "danger" section
 * so it can't be hit by a hand reaching for Advance or Approve Hire
 * It still asks before it acts: a
 * flagged candidate through the confirm dialog on the profile page, an
 * active one through DecisionDialog. */
function EndApplication({
  flagged,
  updating,
  onReject,
}: {
  flagged: boolean;
  updating: boolean;
  onReject: () => void;
}) {
  return (
    <div className="ark-panel__section ark-rail-danger">
      <span className="ark-eyebrow-quiet">End application</span>
      <p className="ark-rail-text">Removes this candidate from the job.</p>
      <div className="ark-rail-actions">
        <Button variant="danger" onClick={onReject} disabled={updating}>
          {flagged ? "Reject Application" : "Reject & Archive"}
        </Button>
      </div>
    </div>
  );
}

/** What happens next, and the buttons that do it — by status. */
function NextMove({
  profile,
  stageName,
  updating,
  advancing,
  advanceError,
  actionError,
  onAdvance,
  onDecide,
  onResolveFlag,
  onReopen,
  onOpenPackage,
}: CandidateSidebarProps & { stageName: string }) {
  let body: ReactNode;

  if (profile.status === "active") {
    // One main action, never two side by side: Advance to the next
    // stage, or -- at Final Decision,
    // or at the end of an older workflow with no Final Decision -- Approve
    // Hire, which records the hire and moves the candidate onto
    // Onboarding in one step. Reject sits apart, in EndApplication below.
    // Every one of them asks before it does anything.
    const decisionTime = profile.current_stage === "final_decision" || !profile.next_stage;
    body = (
      <>
        <span className="ark-eyebrow-quiet">Next step</span>
        <p className="ark-rail-text">{profile.next_steps}</p>
        <div className="ark-rail-actions">
          {decisionTime ? (
            <Button variant="primary" onClick={() => onDecide("hire")} disabled={updating}>
              Approve Hire
            </Button>
          ) : (
            profile.next_stage && (
              <Button variant="primary" onClick={onAdvance} disabled={advancing || updating}>
                {advancing ? "Advancing..." : `Advance to ${profile.next_stage_label ?? stageLabel(profile.next_stage)}`}
                {!advancing && <ArrowRightIcon width={15} height={15} />}
              </Button>
            )
          )}
          {/* Same call under the hood: advanceStage() always tries a real
              advance first, and the skip dialog only opens if the record
              really is incomplete (POST .../transition's
              acknowledged_incomplete). A friendlier door, not a second
              implementation of the gate. */}
          {profile.next_stage && isExamStage(profile.current_stage) && (
            <Button variant="outline" onClick={onAdvance} disabled={advancing || updating}>
              Skip {stageName} for This Job
            </Button>
          )}
        </div>
      </>
    );
  } else if (profile.status === "flagged") {
    // The Skill Matching Agent's review gate. Not a rejection: the DFA is
    // frozen until HR says which way it goes.
    body = (
      <>
        <span className="ark-eyebrow-quiet" style={{ color: "var(--warning-text)" }}>
          Flagged for review
        </span>
        <p className="ark-rail-text">
          Scored {profile.match_score ?? "–"}% against this role, below the fit threshold. This is not an automatic
          rejection. Let them continue, or reject the application.
        </p>
        <div className="ark-rail-actions">
          <Button variant="primary" onClick={() => onResolveFlag("continue")} disabled={updating}>
            Approve to Continue
          </Button>
        </div>
      </>
    );
  } else {
    body = (
      <>
        <span className="ark-eyebrow-quiet">Decision</span>
        <p className="ark-rail-status" data-tone={applicationStatusTone(profile.status)}>
          {STATUS_LABELS[profile.status] ?? profile.status}
        </p>
        <p className="ark-rail-text" style={{ marginTop: 4, color: "var(--ink-600)" }}>
          {profile.decision
            ? "Application closed. The full decision record is at the foot of the page."
            : "Application closed."}
        </p>
        <div className="ark-rail-actions">
          {profile.status === "hired" && (
            <Button variant="secondary" onClick={onOpenPackage}>
              View Pre-Employment Records
            </Button>
          )}
          <Button variant="outline" onClick={onReopen} disabled={updating}>
            Reopen
          </Button>
        </div>
      </>
    );
  }

  return (
    <>
      {body}
      {(advanceError || actionError) && (
        <p style={{ margin: "10px 0 0", fontSize: "var(--text-xs)", color: "crimson" }}>{advanceError ?? actionError}</p>
      )}
    </>
  );
}

/** Read from the resume, so absent until one has been uploaded and
 *  extracted — and each line only when the resume actually had it. */
function Contact({ profile }: { profile: CandidateProfile }) {
  const resume = profile.resume;
  if (!resume) return null;

  const rows: { icon: ReactNode; label: string; value: string; href?: string }[] = [];
  if (resume.email) rows.push({ icon: <MailIcon width={15} height={15} />, label: "Email", value: resume.email, href: `mailto:${resume.email}` });
  if (resume.phone) rows.push({ icon: <PhoneIcon width={15} height={15} />, label: "Phone", value: resume.phone, href: `tel:${resume.phone.replace(/\s+/g, "")}` });
  if (resume.location) rows.push({ icon: <MapPinIcon width={15} height={15} />, label: "Location", value: resume.location });
  if (resume.linkedin_url) rows.push({ icon: <LinkIcon width={15} height={15} />, label: "LinkedIn", value: resume.linkedin_url, href: externalHref(resume.linkedin_url) });
  if (resume.portfolio_url) rows.push({ icon: <LinkIcon width={15} height={15} />, label: "Portfolio", value: resume.portfolio_url, href: externalHref(resume.portfolio_url) });
  if (rows.length === 0) return null;

  return (
    <section className="ark-panel" aria-labelledby="contact-heading">
      <div className="ark-panel__head">
        <div>
          <h2 id="contact-heading" className="ark-panel__title">
            Contact
          </h2>
          <p className="ark-panel__sub">As written on their resume</p>
        </div>
      </div>
      <div className="ark-panel__body">
        <ul className="ark-contact">
          {rows.map((row) => (
            <li key={row.label}>
              {row.icon}
              <span style={{ minWidth: 0 }}>
                <span className="ark-contact__label">{row.label}</span>
                {row.href ? (
                  <a
                    className="ark-contact__value"
                    href={row.href}
                    {...(row.href.startsWith("http") ? { target: "_blank", rel: "noreferrer noopener" } : {})}
                  >
                    {row.value}
                  </a>
                ) : (
                  <span className="ark-contact__value">{row.value}</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

/** A resume's "linkedin.com/in/x" is a link without its scheme. Only
 *  http(s) is ever produced, so a value like "javascript:…" read off a
 *  resume can never become a live link. */
function externalHref(value: string): string {
  const trimmed = value.trim();
  return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed.replace(/^\/+/, "")}`;
}
