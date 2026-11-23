import type { CandidateSynthesis, FactRead } from "../../../../../shared/api/pipeline";
import { shownText } from "../../../../../shared/lib/displayText";
import { Tag } from "../../../../../shared/ui/Tag";
import { FindingList } from "./SynthesisEvidence";
import { Panel } from "./panels";
import { prose } from "./synthesisStyle";

/**
 * Many facts read as "Label: detail" ("Skill match against the job
 * posting: 75.5 out of 100…"), so the first clause is split off and set
 * in bold — it turns a flat run of identical grey lines into something
 * the eye can scan by label.
 */
function splitFact(fact: string): { label: string | null; detail: string } {
  const idx = fact.indexOf(": ");
  // Only treat the head as a label when it is short and not itself a
  // sentence — otherwise a fact like "He left because: …" would bold half
  // a sentence. A period before the colon means it is prose, not a label.
  if (idx > 0 && idx <= 48 && !fact.slice(0, idx).includes(".")) {
    return { label: fact.slice(0, idx + 1), detail: fact.slice(idx + 2) };
  }
  return { label: null, detail: fact };
}

/** Every sentence in the brief is checkable against one of these. The
 * plain-sentence form, kept for a stale brief — its facts describe an
 * older record, so the current `fact_rows` can't stand in for them. */
function FactList({ facts }: { facts: string[] }) {
  return (
    <ul className="ark-fact-list">
      {facts.map((fact) => {
        const { label, detail } = splitFact(shownText(fact));
        return (
          <li key={fact}>
            {label && <b>{label} </b>}
            {detail}
          </li>
        );
      })}
    </ul>
  );
}

/** The fact sheet's sections, in reading order: what was applied for,
 * then each stage's evidence as the candidate met it. */
const FACT_SECTIONS: { key: string; label: string; facts: FactRead["key"][] }[] = [
  { key: "role", label: "Role", facts: ["position"] },
  { key: "resume", label: "Resume", facts: ["skill_match", "requirement_gaps"] },
  {
    key: "interviews",
    label: "Interviews",
    facts: ["rubric", "strongest_area", "weakest_area", "rubric_even", "agreement"],
  },
  { key: "exam", label: "Examination", facts: ["exam"] },
];

function FactRow({ fact }: { fact: FactRead }) {
  const isCount = fact.key === "requirement_gaps";
  return (
    <div className="ark-fact">
      <span className="ark-fact__label">{fact.label}</span>
      {fact.value &&
        (isCount ? (
          <span className="ark-fact__count">{fact.value}</span>
        ) : (
          <span className="ark-fact__value">{fact.value}</span>
        ))}
      {fact.note && <p className="ark-fact__note">{shownText(fact.note)}</p>}
      {fact.scores.length > 0 && (
        <div className="ark-fact__scores">
          {fact.scores.map((score) => (
            <div key={score.name} className="ark-fact__score">
              <span>{score.name}</span>
              <strong>{score.value.toFixed(2)}</strong>
            </div>
          ))}
        </div>
      )}
      {fact.items.length > 0 && (
        <div className="ark-fact__items">
          <FindingList items={fact.items} tone="attention" empty="" />
        </div>
      )}
    </div>
  );
}

/**
 * The fact sheet laid out as a record: one section per stage, each fact
 * as a label with its figure beside it, a list where the fact is a list
 * and a grid where it is a set of scores, so the figures stand out
 * instead of sitting mid-sentence in a wall of grey text.
 */
function FactSheet({ rows }: { rows: FactRead[] }) {
  const sections = FACT_SECTIONS.map((section) => ({
    ...section,
    rows: rows.filter((row) => section.facts.includes(row.key)),
  })).filter((section) => section.rows.length > 0);

  return (
    <div className="ark-factsheet">
      {sections.map((section) => (
        <section key={section.key} className="ark-factsheet__section" aria-label={section.label}>
          <span className="ark-factsheet__heading">{section.label}</span>
          <div className="ark-factsheet__facts">
            {section.rows.map((row) => (
              <FactRow key={row.text} fact={row} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

/** The justification, with the facts it was written from folded beneath
 * it: the verdict and its reasoning are what is read on every candidate,
 * the facts are what is checked when something looks off. */
export function SynthesisBrief({ synthesis, expanded = false }: { synthesis: CandidateSynthesis; expanded?: boolean }) {
  const { brief, fact_sheet, fact_rows } = synthesis;

  if (!brief) {
    // Deliberately shows the facts anyway. They are computed, not
    // generated, so they are available well before there is enough of a
    // record to justify anything — and they are more use to HR than an
    // empty panel.
    if (fact_sheet.length <= 1) return null;
    return (
      <Panel title="What the record shows so far" sub="A written recommendation follows once an evaluator has submitted a scorecard.">
        <FactSheet rows={fact_rows} />
      </Panel>
    );
  }

  return (
    <Panel
      title="Recommendation"
      aside={
        brief.stale ? (
          <Tag tone="amber" dot>
            Record changed since this was written
          </Tag>
        ) : undefined
      }
    >
      <p style={{ margin: 0, fontSize: "var(--text-lg)", fontWeight: 700, lineHeight: "var(--leading-snug)", color: "var(--ink-950)" }}>
        {shownText(brief.verdict)}
      </p>
      <p style={{ ...prose, marginTop: 10, fontSize: "var(--text-base)", color: "var(--ink-700)" }}>{shownText(brief.rationale)}</p>
      {brief.facts.length > 0 && (
        <details className="ark-facts" open={expanded} style={{ marginTop: 14 }}>
          <summary>
            <span className="ark-disclosure" aria-hidden="true" />
            Based on {brief.facts.length} {brief.facts.length === 1 ? "fact" : "facts"} from the record
          </summary>
          {/* A brief that isn't stale was written from exactly the current
              fact sheet (same fingerprint), so the laid-out rows are its
              facts. A stale one describes an older record: its own
              sentences are the only honest account of what it read. */}
          {!brief.stale && fact_rows.length === brief.facts.length ? (
            <FactSheet rows={fact_rows} />
          ) : (
            <FactList facts={brief.facts} />
          )}
        </details>
      )}
    </Panel>
  );
}
