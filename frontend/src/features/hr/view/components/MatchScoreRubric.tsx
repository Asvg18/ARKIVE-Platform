/**
 * Where the resume match score came from: the formula, the rubric, and
 * every requirement's row.
 */

import type { MatchBasis, MatchBreakdown, RequirementScore, RequirementVerdict } from "../../../../shared/api/pipeline";
import { shownText } from "../../../../shared/lib/displayText";
import { Tag, type TagTone } from "../../../../shared/ui/Tag";

const VERDICT: Record<RequirementVerdict, { label: string; tone: TagTone }> = {
  met: { label: "Met", tone: "green" },
  partial: { label: "Partly met", tone: "amber" },
  not_met: { label: "Not met", tone: "neutral" },
};

const BASIS: Record<MatchBasis, { label: string; meaning: string }> = {
  direct: { label: "Direct", meaning: "the resume states what the requirement asks for" },
  equivalent: {
    label: "Equivalent",
    meaning:
      "the same qualification under another name, or one whose major is the required field, for this kind of role. Counts as met",
  },
  related: { label: "Related", meaning: "a neighbouring field that covers part of it. Counts as partly met" },
  transferable: { label: "Transferable", meaning: "experience that shows it indirectly. Counts as partly met" },
  none: { label: "Not addressed", meaning: "nothing in the resume speaks to it" },
};

/** 72.0 → "72", 72.45 → "72.5". */
function fmt(value: number): string {
  return String(Math.round(value * 10) / 10);
}

function pct(weight: number): string {
  return `${Math.round(weight * 100)}%`;
}

/** The formula with its weights, the rubric each requirement is marked
 * against, and per requirement how alike the resume is, the verdict, what
 * it rests on and the resume text it quotes, so a score can be checked
 * rather than trusted. It reads the breakdown stored with the score
 * (MatchBreakdown) and never recomputes it. Shut by default on the
 * Candidate Profile; open in the Pre-201 package, a permanent record. */
export function MatchScoreRubric({ breakdown, open = false }: { breakdown: MatchBreakdown; open?: boolean }) {
  const rows = breakdown.requirements;
  const met = rows.filter((r) => r.verified && r.verdict === "met").length;
  const keywordWeight = 1 - breakdown.semantic_weight;
  const arithmeticWeight = 1 - breakdown.coverage_weight;
  const fullPoints = breakdown.verdict_points.met ?? 1;

  return (
    <details className="ark-rubric" open={open}>
      <summary>
        <span className="ark-disclosure" aria-hidden="true" />
        <span className="ark-rubric__title">How this score was calculated</span>
        {rows.length > 0 && (
          <span className="ark-rubric__detail">
            {met} of {rows.length} requirements met
          </span>
        )}
      </summary>

      <div className="ark-rubric__body">
        {breakdown.arithmetic_score == null ? (
          // scored before the per-requirement method existed
          <p className="ark-rubric__note">
            Scored with the earlier whole-resume method: {pct(breakdown.semantic_weight)} meaning (
            {fmt(breakdown.semantic_score ?? 0)}) and {pct(keywordWeight)} keywords ({fmt(breakdown.keyword_score ?? 0)})
            against the job as a whole, with no per-requirement verdicts.
          </p>
        ) : (
          <div className="ark-rubric__formula" role="group" aria-label="The score's formula">
            <Term
              label="Text similarity"
              value={breakdown.arithmetic_score}
              weight={breakdown.requirement_coverage == null ? undefined : pct(arithmeticWeight)}
              detail={`${pct(breakdown.semantic_weight)} meaning + ${pct(keywordWeight)} keywords, per requirement, averaged`}
            />
            {breakdown.requirement_coverage != null && (
              <>
                <span className="ark-rubric__op" aria-hidden="true">
                  +
                </span>
                <Term
                  label="Requirement coverage"
                  value={breakdown.requirement_coverage}
                  weight={pct(breakdown.coverage_weight)}
                  detail="Verified verdicts: met 1, partly met ½, not met 0, averaged"
                />
              </>
            )}
            <span className="ark-rubric__op" aria-hidden="true">
              =
            </span>
            <Term
              label="Resume match"
              value={breakdown.match_score}
              detail={`Below ${fmt(breakdown.flag_threshold)} is flagged for HR review`}
              strong
            />
          </div>
        )}
        {breakdown.arithmetic_score != null && breakdown.requirement_coverage == null && (
          <p className="ark-rubric__note">No verified verdicts were recorded, so the match is the text similarity alone.</p>
        )}

        {rows.length > 0 && (
          <>
            <div className="ark-rubric__key">
              <div>
                <span className="ark-eyebrow-quiet">Text similarity</span>
                <p>
                  <strong>Meaning:</strong> how close the requirement is to the most similar line of the resume, by AI
                  embeddings, on a 0–100 scale. <strong>Keywords:</strong> how many of the requirement's words the resume
                  uses (BM25), with degree titles and abbreviations read as the same word.
                </p>
              </div>
              <div>
                <span className="ark-eyebrow-quiet">Verdicts</span>
                <ul>
                  {(Object.keys(BASIS) as MatchBasis[])
                    .filter((key) => key !== "none")
                    .map((key) => (
                      <li key={key}>
                        <strong>{BASIS[key].label}:</strong> {BASIS[key].meaning}.
                      </li>
                    ))}
                </ul>
                <p>
                  A verdict earns points only when the resume text it quotes is found in the resume; one that is not, or is
                  still disputed after a second look, earns 0.
                </p>
              </div>
            </div>

            <ol className="ark-rubric__rows">
              {rows.map((row, i) => (
                <RequirementRow key={row.requirement} row={row} index={i + 1} fullPoints={fullPoints} />
              ))}
            </ol>
          </>
        )}
      </div>
    </details>
  );
}

function Term({
  label,
  value,
  weight,
  detail,
  strong = false,
}: {
  label: string;
  value: number;
  weight?: string;
  detail: string;
  strong?: boolean;
}) {
  return (
    <div className="ark-rubric__term" data-strong={strong || undefined}>
      <span className="ark-rubric__term-label">{label}</span>
      <span className="ark-rubric__term-value">
        {fmt(value)}
        {weight && <span className="ark-rubric__term-weight"> × {weight}</span>}
      </span>
      <span className="ark-rubric__term-detail">{detail}</span>
    </div>
  );
}

/** A "Re-checked:" note carries why the verdict was sent back, not what
 * the second look decided (the verdict beside it is that) — said so, or
 * "…which satisfies the requirement" beside a Partly met reads as a
 * contradiction. */
function noteText(note: string): string {
  const reason = note.match(/^Re-checked:\s*(.*)$/s);
  return reason ? `Given a second look. Why it was sent back: ${reason[1]}` : note;
}

function RequirementRow({ row, index, fullPoints }: { row: RequirementScore; index: number; fullPoints: number }) {
  const verdict = VERDICT[row.verdict];
  const quoted = row.verdict !== "not_met" && row.evidence_quote.trim() !== "";
  const disputed = row.note.startsWith("Disputed");

  return (
    <li className="ark-rubric__row">
      <div className="ark-rubric__row-head">
        <span className="ark-rubric__row-index" aria-hidden="true">
          {index}
        </span>
        <span className="ark-rubric__requirement">{row.requirement}</span>
        <span className="ark-rubric__row-score">
          <Tag tone={row.verified ? verdict.tone : "neutral"}>{verdict.label}</Tag>
          <span className="ark-rubric__points">
            {fmt(row.points)} / {fmt(fullPoints)}
            <span className="ark-visually-hidden"> points</span>
          </span>
        </span>
      </div>

      <div className="ark-rubric__row-body">
        <p className="ark-rubric__meta">
          {row.similarity_score != null && (
            <span>
              Similarity <strong>{fmt(row.similarity_score)}</strong> (meaning {fmt(row.semantic_score ?? 0)} · keywords{" "}
              {fmt(row.keyword_score ?? 0)})
            </span>
          )}
          {row.basis !== "none" && <span>Basis: {BASIS[row.basis].label}</span>}
        </p>

        {row.reasoning && <p className="ark-rubric__reasoning">{shownText(row.reasoning)}</p>}

        {quoted ? (
          <blockquote className="ark-rubric__quote">
            <span className="ark-rubric__quote-label">Resume evidence</span>“{row.evidence_quote}”
          </blockquote>
        ) : (
          row.closest_resume_text && (
            <blockquote className="ark-rubric__quote" data-weak>
              <span className="ark-rubric__quote-label">Closest resume line</span>“{row.closest_resume_text}”
            </blockquote>
          )
        )}

        {quoted && !row.verified && !disputed && (
          <p className="ark-rubric__warn">The quoted text was not found in the resume, so this verdict earns no points.</p>
        )}
        {row.note && <p className={disputed ? "ark-rubric__warn" : "ark-rubric__note"}>{shownText(noteText(row.note))}</p>}
      </div>
    </li>
  );
}
