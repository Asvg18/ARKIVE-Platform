import type { InterviewDetail } from "../../../../../shared/api/evaluator";
import { openResumeFile } from "../../../../../shared/api/resume";
import { Avatar } from "../../../../../shared/ui/Avatar";
import { ClockIcon, DocumentIcon } from "../../../../../shared/ui/icons";
import { formatElapsed } from "./interviewFormat";

/** The banner: who is being interviewed, for which job and round, and
 * where the evaluation stands — the applicant page's banner, with the
 * candidate's own photo where that one has the department's mark. */
export function InterviewHero({
  interview,
  upcoming,
  waiting,
  open,
  elapsed,
}: {
  interview: InterviewDetail;
  upcoming: boolean;
  waiting: boolean;
  open: boolean;
  elapsed: number;
}) {
  const status = interview.evaluation
    ? { label: "Evaluation submitted", tone: "green" }
    : upcoming
      ? { label: "Upcoming", tone: undefined }
      : waiting
        ? { label: "Waiting for schedule", tone: undefined }
      : interview.status === "in_progress"
        ? { label: "Awaiting your evaluation", tone: "amber" }
        : { label: "Not evaluated", tone: undefined };

  return (
    <section className="ark-app-hero" aria-labelledby="interview-hero-title">
      <span className="ark-app-hero__avatar">
        <Avatar name={interview.applicant_name} size={52} src={interview.applicant_avatar_url} />
      </span>

      <div className="ark-app-hero__text">
        <span className="ark-app-hero__eyebrow">Interview evaluation</span>
        <h1 id="interview-hero-title" className="ark-app-hero__title">
          {interview.applicant_name}
        </h1>
        <div className="ark-app-hero__meta">
          <strong>{interview.job_title}</strong>
          <span className="ark-app-hero__sep" aria-hidden="true" />
          <span>{interview.stage_label}</span>
        </div>
      </div>

      <div className="ark-app-hero__side">
        <span className="ark-app-hero__status" data-tone={status.tone}>
          {status.label}
        </span>
        {open && (
          <span className="ark-app-hero__timer" title="Time since you opened this page">
            <ClockIcon width={13} height={13} aria-hidden="true" />
            Reviewing for {formatElapsed(elapsed)}
          </span>
        )}
      </div>
    </section>
  );
}

/** The candidate's resume, and nothing the AI made of it. The match score
 * and AI-picked skills are never shown to evaluators: a person who has
 * seen the machine's verdict is anchored to it, and this system's whole
 * claim is that the human judgement (C3) and the AI's reads are
 * independent signals that can be compared. The server doesn't send them. */
export function CandidatePanel({ interview, token }: { interview: InterviewDetail; token: string | null }) {
  return (
    <section className="ark-panel" aria-labelledby="eval-candidate-title">
      <div className="ark-panel__head">
        <h2 id="eval-candidate-title" className="ark-panel__title">Candidate</h2>
      </div>
      <div className="ark-panel__body ark-eval-candidate">
        {interview.resume ? (
          <button
            type="button"
            className="ark-eval-file"
            onClick={() => openResumeFile(`/evaluator/applications/${interview.application_id}/resume-file`, token)}
          >
            <span className="ark-eval-file__icon" aria-hidden="true">
              <DocumentIcon width={16} height={16} />
            </span>
            <span className="ark-eval-file__text">
              <span className="ark-eval-file__name">{interview.resume.original_filename}</span>
              <span className="ark-eval-file__hint">Resume</span>
            </span>
          </button>
        ) : (
          <p className="ark-panel__empty">No resume uploaded yet.</p>
        )}
      </div>
    </section>
  );
}
