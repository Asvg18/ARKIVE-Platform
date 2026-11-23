import { useId, useLayoutEffect, useRef, useState } from "react";
import type { CandidateSynthesis } from "../../../../../shared/api/pipeline";
import { shownText } from "../../../../../shared/lib/displayText";
import { Tag } from "../../../../../shared/ui/Tag";
import { ArrowRightIcon, CheckIcon, MinusIcon } from "../../../../../shared/ui/icons";
import { MatchScoreRubric } from "../MatchScoreRubric";
import { Panel } from "./panels";
import { prose } from "./synthesisStyle";

/** The evidence panel's anchor — where the verdict's resume-gap fact leads. */
export const SYNTHESIS_EVIDENCE_ID = "synthesis-evidence";

/** Which of the resume read's two lists is showing. */
export type EvidenceView = "evidenced" | "gaps";

/** The tabs holding the source records behind the evidence figures. */
export type EvidenceSource = "documents" | "examinations";

function ordinal(n: number): string {
  const tens = n % 100;
  if (tens >= 11 && tens <= 13) return `${n}th`;
  return `${n}${({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th"}`;
}

/** One headline number from an earlier stage, with what it means and a
 * way through to the record it came from. */
function EvidenceFigure({
  label,
  value,
  pct,
  reading,
  action,
}: {
  label: string;
  value: string;
  pct: number;
  reading: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <div className="ark-evidence-figure">
      <div className="ark-evidence-figure__head">
        <span className="ark-evidence-figure__label">{label}</span>
        {action && (
          <button type="button" className="ark-go" onClick={action.onClick}>
            {action.label}
            <ArrowRightIcon width={13} height={13} aria-hidden="true" />
          </button>
        )}
      </div>
      <span className="ark-evidence-figure__value">{value}</span>
      <div className="ark-evidence-figure__meter" aria-hidden="true">
        <span style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
      </div>
      <p className="ark-evidence-figure__reading">{reading}</p>
    </div>
  );
}

/** The resume read's findings, one per row, marked by which way each
 * points — the same green/amber the verdict's facts use. */
export function FindingList({ items, tone, empty }: { items: string[]; tone: "positive" | "attention"; empty: string }) {
  if (items.length === 0) return <p className="ark-findings__empty">{empty}</p>;
  const Mark = tone === "positive" ? CheckIcon : MinusIcon;
  return (
    <ul className="ark-findings" data-tone={tone}>
      {items.map((item) => (
        <li key={item}>
          <span className="ark-findings__mark" aria-hidden="true">
            <Mark width={11} height={11} strokeWidth={3} />
          </span>
          <span>{shownText(item)}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * What the stages before the interview chain found.
 *
 * The numbers sit side by side as short figures at the top, each leading
 * to its source record (the examination is one number and a sentence, so
 * a column of its own would stand half empty). The resume read takes the
 * full width, its two lists behind one switch. The Pre-201 package
 * (`expanded`) shows both lists: a permanent record hides nothing.
 *
 * The switch is controlled when `view` is given — the Candidate Profile
 * holds it so the verdict's "unaddressed requirements" link can open the
 * gaps directly.
 */
export function SynthesisEvidence({
  evidence,
  topSkills = [],
  expanded = false,
  view,
  onViewChange,
  onOpenSource,
}: {
  evidence: CandidateSynthesis["evidence"];
  /** The skills the resume read found, shown with the resume they came from. */
  topSkills?: string[];
  expanded?: boolean;
  view?: EvidenceView;
  onViewChange?: (view: EvidenceView) => void;
  onOpenSource?: (source: EvidenceSource) => void;
}) {
  const [ownView, setOwnView] = useState<EvidenceView>("evidenced");
  const findingsId = useId();
  const current = view ?? ownView;
  const setView = onViewChange ?? setOwnView;

  const hasResume = evidence.match_score != null;
  const hasExam = evidence.exam_score != null;
  if (!hasResume && !hasExam) return null;

  const strengths = evidence.match_strengths;
  const gaps = evidence.match_gaps;
  const hasFindings = hasResume && (strengths.length > 0 || gaps.length > 0);
  // The Critic did not sign this resume read off, or a verdict is still
  // disputed: say so where the findings are, so they are not read as
  // established (the score itself only counts verdicts that held up).
  const unverified = hasResume && Boolean(evidence.match_unverified);
  const disputed = hasResume ? (evidence.match_disputed ?? []) : [];
  const ranked = evidence.exam_rank != null && evidence.exam_cohort != null && evidence.exam_cohort > 1;

  const views: { key: EvidenceView; label: string; tone: "positive" | "attention"; items: string[]; empty: string }[] = [
    { key: "evidenced", label: "Evidenced", tone: "positive", items: strengths, empty: "The resume read recorded no strengths against this job." },
    { key: "gaps", label: "Not evidenced", tone: "attention", items: gaps, empty: "The resume read recorded no gaps against this job." },
  ];
  const shown = views.find((v) => v.key === current) ?? views[0];

  return (
    <Panel id={SYNTHESIS_EVIDENCE_ID} title="Evidence from earlier stages" bodyless>
      <div className="ark-evidence">
        <div className="ark-evidence__figures">
          {hasResume && (
            <EvidenceFigure
              label="Resume match"
              value={`${evidence.match_score}%`}
              pct={evidence.match_score!}
              reading={shownText(evidence.match_reading)}
              action={onOpenSource && { label: "Open the resume", onClick: () => onOpenSource("documents") }}
            />
          )}
          {hasExam && (
            <EvidenceFigure
              label="Examination"
              value={`${evidence.exam_score} / 100`}
              pct={evidence.exam_score!}
              reading={
                ranked
                  ? `Ranked ${ordinal(evidence.exam_rank!)} of the ${evidence.exam_cohort} candidates who sat it for this job.`
                  : "The only candidate to have sat this job's examination so far."
              }
              action={onOpenSource && { label: "Open the examination", onClick: () => onOpenSource("examinations") }}
            />
          )}
        </div>

        {hasResume && evidence.match_breakdown && <MatchScoreRubric breakdown={evidence.match_breakdown} open={expanded} />}

        {hasResume && topSkills.length > 0 && (
          <div className="ark-evidence__block">
            <span className="ark-eyebrow-quiet">Skills read from the resume</span>
            <div className="ark-chips">
              {topSkills.map((skill) => (
                <Tag key={skill}>{skill}</Tag>
              ))}
            </div>
          </div>
        )}

        {(unverified || disputed.length > 0) && (
          <div className="ark-callout ark-callout--warn" role="note">
            <div>
              {unverified && (
                <p style={{ margin: 0 }}>
                  <strong>Unverified: check the resume.</strong> The Critic Agent could not confirm this resume read against
                  the evidence, so the strengths and gaps below may be wrong. Requirement verdicts were audited separately.
                </p>
              )}
              {disputed.length > 0 && (
                <>
                  <p style={{ margin: unverified ? "var(--space-2) 0 0" : 0 }}>
                    <strong>Disputed requirements.</strong> These verdicts were checked twice and still disagree with the resume:
                  </p>
                  <ul style={{ margin: "var(--space-1) 0 0", paddingLeft: "var(--space-5)" }}>
                    {disputed.map((item) => (
                      <li key={item.requirement}>
                        <strong>{item.requirement}</strong>
                        <br />
                        {shownText(item.note)}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          </div>
        )}

        {hasFindings &&
          (expanded ? (
            <div className="ark-evidence__lists">
              {views.map((v) => (
                <div key={v.key} className="ark-evidence__block">
                  <span className="ark-eyebrow-quiet">
                    {v.key === "evidenced" ? "What the resume evidenced" : "What it did not evidence"}
                    {unverified && " (unverified)"}
                  </span>
                  <FindingList items={v.items} tone={v.tone} empty={v.empty} />
                </div>
              ))}
            </div>
          ) : (
            <div className="ark-evidence__block">
              <span className="ark-eyebrow-quiet">Against the job's requirements</span>
              <div className="ark-tabs" role="tablist" aria-label="Resume read against the job's requirements">
                {views.map((v) => (
                  <button
                    key={v.key}
                    type="button"
                    role="tab"
                    id={`${findingsId}-${v.key}`}
                    aria-selected={current === v.key}
                    aria-controls={`${findingsId}-panel`}
                    className="ark-tab"
                    onClick={() => setView(v.key)}
                  >
                    <span className="ark-tab__dot" data-tone={v.tone} aria-hidden="true" />
                    {v.label}
                    {unverified && <span className="ark-tab__flag">Unverified</span>}
                    <span className="ark-tab__count">{v.items.length}</span>
                  </button>
                ))}
              </div>
              <div role="tabpanel" id={`${findingsId}-panel`} aria-labelledby={`${findingsId}-${shown.key}`}>
                <FindingList items={shown.items} tone={shown.tone} empty={shown.empty} />
              </div>
            </div>
          ))}
      </div>
    </Panel>
  );
}

/** Prose shown a few lines at a time, with a control only when there is
 * more than fits. */
export function ClampedText({ text, lines = 3, label }: { text: string; lines?: number; label: string }) {
  const [open, setOpen] = useState(false);
  const [overflows, setOverflows] = useState(false);
  const ref = useRef<HTMLParagraphElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (el && !open) setOverflows(el.scrollHeight > el.clientHeight + 1);
  }, [text, open]);

  return (
    <>
      <p
        ref={ref}
        className="ark-clamp"
        data-open={open || undefined}
        style={{ ...prose, whiteSpace: "pre-wrap", ["--clamp-lines" as string]: lines }}
      >
        {text}
      </p>
      {(overflows || open) && (
        <button type="button" className="ark-more" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          {open ? "Show less" : `Read the full ${label}`}
        </button>
      )}
    </>
  );
}
