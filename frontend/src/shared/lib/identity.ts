/** Stable identity colours and initials for what HR scans in a list: job
 * openings, departments, people. Tinting by department makes colour carry
 * a fact that repeats across screens, so a row is findable without being
 * read; the accent stays reserved for the item you selected. */

const PALETTE = [
  "var(--dept-1)",
  "var(--dept-2)",
  "var(--dept-3)",
  "var(--dept-4)",
  "var(--dept-5)",
  "var(--dept-6)",
  "var(--dept-7)",
  "var(--dept-8)",
  "var(--dept-9)",
  "var(--dept-10)",
  "var(--dept-11)",
  "var(--dept-12)",
];

/** FNV-1a. Chosen over `split('').reduce(...)` on char codes because that
 * hashes anagrams and near-anagrams to neighbouring buckets, and a
 * department list is full of near-anagrams ("Library Services" /
 * "Library Sciences"). */
function hash(value: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < value.length; i++) {
    h ^= value.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

function key(value: string): string {
  return value.trim().toLowerCase();
}

/** Colours for a known set of departments, guaranteed distinct.
 *
 * The first version hashed each department straight into the palette,
 * which measured badly on real data: **nine departments produced six
 * colours**, with Computing and Community Engagement -- two rows apart
 * in the rail -- landing on the same umber. Not bad luck to tune away;
 * any hash-into-buckets scheme collides by the birthday problem, and
 * widening the palette barely helps.
 *
 * Distinctness *within the list you're looking at* is the actual
 * requirement, so assign by rank instead. Sorting first keeps it
 * stable -- the mapping depends on the set of departments, not the
 * order the server returned jobs in, so the same screen renders the
 * same colours every load, and two screens showing the same jobs agree.
 * Only past PALETTE.length departments does anything repeat, and then
 * it degrades evenly instead of clustering. */
export function departmentPalette(departments: Iterable<string | null | undefined>): Map<string, string> {
  const unique = [...new Set([...departments].filter((d): d is string => !!d && d.trim() !== "").map(key))].sort();
  return new Map(unique.map((dept, i) => [dept, PALETTE[i % PALETTE.length]]));
}

/** Look a department up in a palette built by `departmentPalette`, with a
 * hashed fallback for a value the map has not seen — a job loaded on its
 * own, outside any list. */
export function colorFor(
  palette: Map<string, string>,
  department: string | null | undefined
): string {
  if (!department) return "var(--ink-400)";
  return palette.get(key(department)) ?? identityColor(department);
}

/** Standalone colour for a single value with no list to rank it against —
 * a candidate's avatar, one job on its own page. Collisions do not matter
 * here because nothing sits beside it to be confused with. */
export function identityColor(value: string | null | undefined): string {
  if (!value) return "var(--ink-400)";
  return PALETTE[hash(key(value)) % PALETTE.length];
}

/** Up to two initials for a tile.
 *
 * Skips the small words a job title is full of — "Assistant to the
 * Director" should read AD, not AT. Falls back to the first two letters
 * of a single word, so "Onboarding" gives ON rather than a lonely O. */
const SKIP = new Set(["of", "the", "and", "for", "to", "in", "on", "at", "a", "an", "&", "-"]);

export function initials(value: string | null | undefined): string {
  if (!value) return "–";
  const words = value
    .replace(/[()[\]{}/,.]/g, " ")
    .split(/\s+/)
    .map((w) => w.trim())
    .filter((w) => w.length > 0 && !SKIP.has(w.toLowerCase()));

  if (words.length === 0) return value.slice(0, 2).toUpperCase();
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}
