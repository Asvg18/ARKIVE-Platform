/**
 * Long dashes and an accented "résumé" taken out of text ARKIVE shows but
 * did not word itself: what the AI wrote, and records frozen as made.
 */

const LONG_DASH = "\u2014";
const SHORT_DASH = "\u2013";

/** Older stage names, as frozen records still hold them. */
const RENAMED_STAGES: readonly [string, string][] = [
  [`Interview ${LONG_DASH} HR Administrator`, "HR Administrator Interview"],
  [`Interview ${LONG_DASH} Dept. Head`, "Department Head Interview"],
  [`Interview ${LONG_DASH} VP`, "VP Interview"],
];

/** Spaces and tabs, never a line break: a dash's own line stays its own. */
const GAP = "[^\\S\\r\\n]*";
const DASHES = `${LONG_DASH}+`;

const ONLY_DASHES = new RegExp(`^\\s*${DASHES}\\s*$`);
const RANGE = new RegExp(`(\\d)${GAP}${DASHES}${GAP}(?=\\d)`, "g");
const LINE_START = new RegExp(`^${GAP}${DASHES}${GAP}`, "gm");
const LINE_END = new RegExp(`${GAP}${DASHES}${GAP}$`, "gm");
/** Before a mark that already separates: the dash just goes. */
const BEFORE_MARK = new RegExp(`${GAP}${DASHES}${GAP}(?=[,.;:!?)\\]"'\u2019\u201d])`, "g");
/** After one that opens: the dash goes, and so does its space. */
const AFTER_OPENING = new RegExp(`([(\\[\u2018\u201c])${GAP}${DASHES}${GAP}`, "g");
/** After one that ends a clause or sentence: the dash goes, one space stays. */
const AFTER_CLOSING = new RegExp(`([,.;:!?])${GAP}${DASHES}${GAP}`, "g");
const BETWEEN_WORDS = new RegExp(`${GAP}${DASHES}${GAP}`, "g");

const ACCENTED_RESUME = /RÉSUMÉ|Résumé|résumé/g;
const UNACCENTED: Record<string, string> = { "RÉSUMÉ": "RESUME", "Résumé": "Resume", "résumé": "resume" };

/** `text` as it should be shown: no long dash in it, and "resume"
 * without accents. Text with neither comes back untouched.
 *
 * Cleaned when shown, never where stored, so the AI's own copy (and
 * everything an AI step reads later) stays as written. Never used on text
 * a person typed (remarks, reasons, letters, answers).
 *
 * Between two words a long dash becomes a comma; between two numbers, a
 * short dash (a range); at the start or end of a line, or beside other
 * punctuation, it goes. Text that is only a dash is an empty value, shown
 * as the short dash. */
export function shownText(text: string): string;
export function shownText(text: string | null | undefined): string | null | undefined;
export function shownText(text: string | null | undefined): string | null | undefined {
  if (!text) return text;
  text = text.replace(ACCENTED_RESUME, (word) => UNACCENTED[word]);
  if (!text.includes(LONG_DASH)) return text;
  if (ONLY_DASHES.test(text)) return SHORT_DASH;
  let shown = text;
  for (const [before, after] of RENAMED_STAGES) shown = shown.split(before).join(after);
  return shown
    .replace(RANGE, `$1${SHORT_DASH}`)
    .replace(LINE_START, "")
    .replace(LINE_END, "")
    .replace(BEFORE_MARK, "")
    .replace(AFTER_OPENING, "$1")
    .replace(AFTER_CLOSING, "$1 ")
    .replace(BETWEEN_WORDS, ", ");
}
