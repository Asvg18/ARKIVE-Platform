/** The homepage's fixed sections: headings, the transparency band, the
 *  hiring process, the closing call to action and the footer. */

import type { ReactNode } from "react";
import { APPLICANT_STATUS_LABELS } from "../../../../shared/lib/stageLabels";
import { applicationStatusTone } from "../../../../shared/lib/statusTags";
import type { ApplicationDetail } from "../../../../shared/api/applicant";
import { Button } from "../../../../shared/ui/Button";
import { ArrowRightIcon } from "../../../../shared/ui/icons";
import { Logo } from "../../../../shared/ui/Logo";
import { Tag } from "../../../../shared/ui/Tag";
import { ApplicationOrbit } from "./ApplicationOrbit";

/** A section's title block: eyebrow, serif title, one line beneath. */
export function SectionHead({ eyebrow, title, sub, align = "center" }: { eyebrow: string; title: string; sub?: ReactNode; align?: "center" | "start" }) {
  return (
    <div className="ark-home__head" data-align={align}>
      <span className="ark-home__eyebrow">{eyebrow}</span>
      <h2 className="ark-home__h2">{title}</h2>
      {sub && <p className="ark-home__sub">{sub}</p>}
    </div>
  );
}

/**
 * The one thing this board can promise that a conventional one cannot:
 * an applicant sees which stage they have reached. Shown as the screens
 * themselves, turning on a ring — made-up applications to real kinds of
 * job; no real person's application is on the public page.
 */
export function TransparencyBand({ role, onNavigate }: { role: string | null; onNavigate: (to: string) => void }) {
  return (
    <section className="ark-home__band">
      <div className="ark-home__container ark-band">
        <div className="ark-band__copy">
          <span className="ark-home__eyebrow">Your application, in plain sight</span>
          <h2 className="ark-home__h2">
            Know where you stand,
            <br />
            at every stage.
          </h2>
          <p className="ark-home__sub">
            Applications usually vanish into an inbox. Here every stage is recorded as it happens, and your dashboard shows
            the one you've reached, from upload to the final decision.
          </p>
          <div className="ark-band__actions">
            {role === null && (
              <>
                <Button variant="primary" onClick={() => onNavigate("/signup")}>
                  Create an Account
                </Button>
                <Button variant="secondary" onClick={() => onNavigate("/login")}>
                  Track My Application
                </Button>
              </>
            )}
            {role === "applicant" && (
              <Button variant="primary" onClick={() => onNavigate("/applicant")}>
                Open My Applications
              </Button>
            )}
          </div>
        </div>

        <ApplicationOrbit />
      </div>
    </section>
  );
}

/**
 * What happens after you apply. Every job generates its own workflow, so
 * this describes the shape rather than claiming a fixed number of stages
 * — the exact sequence appears on the job itself.
 */
export function HiringProcess() {
  const steps: Array<[string, string]> = [
    ["Apply", "Upload your resume and a short letter of intent."],
    ["Pre-screening", "Answer a few role-specific questions in writing."],
    ["Examination", "Sit a written assessment, at a slot you choose."],
    ["Interviews", "Meet HR, the department head, and a vice president."],
    ["Decision", "A hiring decision, recorded with its reasoning."],
  ];
  return (
    <section id="process" className="ark-home__section">
      <div className="ark-home__container">
        <SectionHead
          eyebrow="What to expect"
          title="The hiring process"
          sub="Every position defines its own sequence. The exact stages for a role are listed on that job. Most follow this shape."
        />
        <ol className="ark-process">
          {steps.map(([title, detail], i) => (
            <li key={title} className="ark-process__step">
              <span className="ark-process__n">{String(i + 1).padStart(2, "0")}</span>
              <span className="ark-process__title">{title}</span>
              <p className="ark-process__detail">{detail}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

/** The closing call to action. Hidden once signed in — inviting someone to
 *  create an account they are currently using reads as a broken page. */
export function ClosingCta({ signedIn, onCreateAccount }: { signedIn: boolean; onCreateAccount: () => void }) {
  if (signedIn) return null;
  return (
    <section className="ark-home__cta">
      <div className="ark-home__container ark-home__cta-inner">
        <div>
          <h2 className="ark-home__cta-title">Ready to start your application?</h2>
          <p className="ark-home__cta-text">
            Create an account to apply, book your examination, and follow every stage of your application as it happens.
          </p>
        </div>
        <button type="button" className="ark-home__cta-btn" onClick={onCreateAccount}>
          Create Account
          <ArrowRightIcon width={16} height={16} aria-hidden="true" />
        </button>
      </div>
    </section>
  );
}

/** Site footer. Deliberately carries no Privacy Policy / Terms links, nor a
 *  phone number or social icons: none of those exist yet, and a link to
 *  nothing is worse than no link. Every link here goes somewhere real. */
export function SiteFooter({
  signedIn,
  dashboardPath,
  onNavigate,
}: {
  signedIn: boolean;
  dashboardPath: string | null;
  onNavigate: (to: string) => void;
}) {
  const go = (to: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    onNavigate(to);
  };
  return (
    <footer className="ark-home__footer">
      <div className="ark-home__container ark-home__footer-grid">
        <div className="ark-home__footer-brand">
          <div className="ark-home__brand ark-home__brand--footer">
            <Logo size={30} />
            <span>ARKIVE</span>
          </div>
          <p>
            The hiring system of the Human Resources Department, Manuel S. Enverga University Foundation, Lucena City.
          </p>
        </div>
        <nav aria-label="Explore">
          <span className="ark-home__footer-head">Explore</span>
          <a href="#openings">Open positions</a>
          <a href="#process">Hiring process</a>
        </nav>
        <nav aria-label="Your account">
          <span className="ark-home__footer-head">Your account</span>
          {signedIn && dashboardPath ? (
            <a href={dashboardPath} onClick={go(dashboardPath)}>
              Go to dashboard
            </a>
          ) : (
            <>
              <a href="/login" onClick={go("/login")}>
                Sign in
              </a>
              <a href="/signup" onClick={go("/signup")}>
                Create an account
              </a>
              <a href="/forgot-password" onClick={go("/forgot-password")}>
                Forgot password
              </a>
            </>
          )}
        </nav>
      </div>
      <div className="ark-home__container ark-home__footer-base">
        <span>&copy; {new Date().getFullYear()} Manuel S. Enverga University Foundation. All rights reserved.</span>
      </div>
    </footer>
  );
}

/**
 * One application, small enough to sit three-to-a-card.
 *
 * Shows the two things a returning applicant came to find out: which job,
 * and how far along it is. The fraction is honest about the fact that
 * different jobs run different-length pipelines — "6 of 10" means
 * something only alongside its own total.
 */
export function MiniApplication({ application }: { application: ApplicationDetail }) {
  const stages = application.stage_instances;
  const done = stages.filter((s) => s.status === "complete").length;
  const currentIndex = stages.findIndex((s) => s.status === "in_progress");
  const current = currentIndex >= 0 ? stages[currentIndex] : null;
  const closed = application.status !== "active" && application.status !== "flagged";

  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
        <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--ink-900)", minWidth: 0,
                      whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {application.job_title}
        </div>
        {/* The status takes its tag and colour from statusTags, as on the
            applicant's dashboard and every other screen. */}
        <Tag tone={applicationStatusTone(application.status)} dot>
          {APPLICANT_STATUS_LABELS[application.status] ?? application.status}
        </Tag>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 5 }}>
        <div style={{ flex: 1, height: 3, borderRadius: 999, background: "var(--surface-bg-alt)", overflow: "hidden" }}>
          <div style={{
            width: `${Math.round((done / Math.max(stages.length, 1)) * 100)}%`,
            height: "100%",
            background: application.status === "hired" ? "var(--success-text)" : "var(--accent)",
          }} />
        </div>
        <span style={{ fontSize: "var(--text-2xs)", color: "var(--ink-600)", whiteSpace: "nowrap",
                       fontVariantNumeric: "tabular-nums" }}>
          {done} of {stages.length}
        </span>
      </div>
      {/* Only live applications name a stage. On a closed one the status
          beside the title already says Hired or Rejected. */}
      {!closed && (
        <div style={{ fontSize: "var(--text-2xs)", color: "var(--ink-700)", marginTop: 4 }}>
          {current ? current.label : "Not started"}
        </div>
      )}
    </div>
  );
}

/**
 * A row of segments, one per stage in this job's generated workflow —
 * the shape someone sees while browsing is the shape they later move
 * through, and every requisition really does run its own length.
 */
export function StageRail({ count }: { count: number }) {
  if (!count) return null;
  return (
    <span className="ark-job__rail" title={`${count} stages`}>
      <span className="ark-job__rail-bars" aria-hidden="true">
        {Array.from({ length: count }).map((_, i) => (
          <span key={i} data-first={i === 0 || undefined} />
        ))}
      </span>
      {count}-stage process
    </span>
  );
}
