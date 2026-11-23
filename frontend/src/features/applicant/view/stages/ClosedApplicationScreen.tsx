import { Link } from "react-router-dom";
import type { ApplicationDetail } from "../../../../shared/api/applicant";
import { getApplicantSkillMatchPayload } from "../../../../shared/api/skillMatch";
import { Button } from "../../../../shared/ui/Button";
import { ArrowRightIcon, InfoIcon, LogOutIcon } from "../../../../shared/ui/icons";

/**
 * The screen for an application that has ended without an offer — the
 * applicant was unlikely to progress, or withdrew. A bare "closed" line
 * would tell someone who had sat an exam and an interview nothing they
 * could use.
 *
 * So, in order: what happened, said kindly and plainly; how far they got
 * (real figures from the application — the stage they reached, their
 * exam score); and where to go next (the openings the skill-matching pass
 * already suggested for them, and the job browser). Nothing here is
 * invented: a figure the application doesn't have is simply left out.
 *
 * White card, colour only on the mark that carries the meaning (the icon
 * and the one-word status), as elsewhere in the portal.
 */
export function ClosedApplicationScreen({ application }: { application: ApplicationDetail }) {
  const withdrawn = application.status === "withdrawn";
  const stages = application.stage_instances;

  // Where it stopped: the stage that was live when it closed, or failing
  // that the last one completed.
  let reachedIndex = stages.findIndex((s) => s.status === "in_progress");
  if (reachedIndex < 0) {
    for (let i = stages.length - 1; i >= 0; i--) {
      if (stages[i].status === "complete") {
        reachedIndex = i;
        break;
      }
    }
  }
  const reached = reachedIndex >= 0 ? stages[reachedIndex] : null;
  const completed = stages.filter((s) => s.status === "complete").length;
  const exam = Object.values(application.examination_results)[0] ?? null;
  const suggestions = getApplicantSkillMatchPayload(stages)?.suggested_requisitions ?? [];

  return (
    <div className="ark-outcome" data-tone={withdrawn ? "neutral" : "red"}>
      <div className="ark-outcome__head">
        <span className="ark-outcome__icon" aria-hidden="true">
          {withdrawn ? <LogOutIcon width={22} height={22} /> : <InfoIcon width={22} height={22} />}
        </span>
        <div className="ark-outcome__intro">
          <span className="ark-outcome__eyebrow">{withdrawn ? "Withdrawn" : "Unlikely to progress"}</span>
          <h2 className="ark-outcome__title">
            {withdrawn ? "You withdrew this application" : `Thank you for applying for ${application.job_title}`}
          </h2>
          <p className="ark-outcome__text">
            {withdrawn ? (
              <>
                You're no longer being considered for <strong>{application.job_title}</strong>. Your other applications
                aren't affected.
              </>
            ) : (
              <>
                The hiring team has reviewed your application and won't be taking it further at this stage. We
                appreciate the time you gave to each step. There may be other openings that suit you.
              </>
            )}
          </p>
        </div>
      </div>

      <div className="ark-outcome__stats">
        {reached && (
          <div className="ark-outcome__stat">
            <span className="ark-outcome__stat-label">Furthest stage</span>
            <span className="ark-outcome__stat-value">{reached.label}</span>
            <span className="ark-outcome__stat-note">
              Stage {reachedIndex + 1} of {stages.length}
            </span>
          </div>
        )}
        <div className="ark-outcome__stat">
          <span className="ark-outcome__stat-label">Stages completed</span>
          <span className="ark-outcome__stat-value">
            {completed} of {stages.length}
          </span>
          <span className="ark-outcome__stat-note">{application.job_department}</span>
        </div>
        {exam && (
          <div className="ark-outcome__stat">
            <span className="ark-outcome__stat-label">{exam.label} score</span>
            <span className="ark-outcome__stat-value">{exam.score} / 100</span>
            {application.exam_percentile != null && (
              <span className="ark-outcome__stat-note">Better than {application.exam_percentile}% of applicants</span>
            )}
          </div>
        )}
      </div>

      <div className="ark-outcome__next">
        <h3 className="ark-outcome__section-title">
          {suggestions.length > 0 ? "Openings that may suit you" : "Keep exploring"}
        </h3>
        <p className="ark-outcome__section-sub">
          {suggestions.length > 0
            ? "Suggested from your resume when you applied."
            : "New faculty and staff openings are posted regularly."}
        </p>

        {suggestions.length > 0 && (
          <div className="ark-outcome__jobs">
            {suggestions.map((s) => (
              <Link key={s.requisition_id} to={`/applicant/jobs?job=${s.requisition_id}`} className="ark-outcome__job">
                <span>
                  <span className="ark-outcome__job-title">{s.title}</span>
                  <span className="ark-outcome__job-dept">{s.department}</span>
                </span>
                <ArrowRightIcon width={16} height={16} aria-hidden="true" />
              </Link>
            ))}
          </div>
        )}

        <div className="ark-outcome__actions">
          <Link to="/applicant/jobs" style={{ textDecoration: "none" }}>
            <Button variant="primary">Find Jobs</Button>
          </Link>
          <Link to="/applicant" className="ark-go">
            Back to My Applications
          </Link>
        </div>
      </div>
    </div>
  );
}
