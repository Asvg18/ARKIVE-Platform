/** The user manual, read from manual.md and split into the parts the Help
 * page shows (29 Oct 2026).
 *
 * The manual is written and reviewed as a document outside the codebase,
 * then exported to Markdown. Keeping that export as one file, rather than
 * retyping it into components, means an updated manual is one file
 * replaced, and the in-app help can never drift from the copy HR signed
 * off. The parser only knows the few shapes that document uses: `##`
 * sections, `###` topics, paragraphs, numbered, bulleted and checkbox
 * lists, pipe tables, and **bold**. */

import source from "./manual.md?raw";

/** Who a part of the manual is for. The Help page puts a role's own
 *  guide first and leaves the other roles' guides out until asked. */
export type Audience = "all" | "applicant" | "hr" | "evaluator";

export type Block =
  | { kind: "p"; text: string }
  | { kind: "ol" | "ul" | "check"; items: string[] }
  | { kind: "table"; head: string[]; rows: string[][] };

export interface Topic {
  id: string;
  title: string;
  audience: Audience;
  blocks: Block[];
}

export interface Section {
  id: string;
  /** "Section 3", or null for the conclusion. */
  label: string | null;
  title: string;
  audience: Audience;
  blocks: Block[];
  topics: Topic[];
}

/** The role guides, by the slug of their heading. */
const SECTION_AUDIENCE: Record<string, Audience> = {
  "applicant-guide": "applicant",
  "hr-admin-guide": "hr",
  "evaluator-guide": "evaluator",
};

/** The FAQ's per-role groups. The rest of the FAQ is for everyone. */
const TOPIC_AUDIENCE: Record<string, Audience> = {
  applying: "applicant",
  "hr-admins": "hr",
  evaluators: "evaluator",
};

/** "3.6 Booking an Exam" -> "booking-an-exam". The numbers are left out
 *  so a link to a topic survives the manual being renumbered. */
export function slugify(heading: string): string {
  return heading
    .replace(/^Section \d+:\s*/, "")
    .replace(/^\d+(\.\d+)*\s+/, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function splitRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((cell) => cell.trim());
}

/** The blocks in a run of lines with no headings in it. */
function parseBlocks(lines: string[]): Block[] {
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    if (line.startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        rows.push(splitRow(lines[i]));
        i++;
      }
      // the second row is the |---| divider under the header
      blocks.push({ kind: "table", head: rows[0], rows: rows.slice(2) });
      continue;
    }
    const list = /^(\d+\.|- \[ \]|-)\s+/.exec(line);
    if (list) {
      const kind = list[1] === "-" ? "ul" : list[1] === "- [ ]" ? "check" : "ol";
      const items: string[] = [];
      while (i < lines.length) {
        const item = /^(\d+\.|- \[ \]|-)\s+(.*)$/.exec(lines[i]);
        if (!item) break;
        items.push(item[2]);
        i++;
      }
      blocks.push({ kind, items });
      continue;
    }
    const text: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(\||\d+\.\s|-\s)/.test(lines[i])) {
      text.push(lines[i].trim());
      i++;
    }
    blocks.push({ kind: "p", text: text.join(" ") });
  }
  return blocks;
}

export function parseManual(markdown: string): Section[] {
  const sections: Section[] = [];
  let section: Section | null = null;
  let topic: Topic | null = null;
  let buffer: string[] = [];

  const flush = () => {
    const blocks = parseBlocks(buffer);
    buffer = [];
    if (topic) topic.blocks.push(...blocks);
    else if (section) section.blocks.push(...blocks);
  };

  for (const line of markdown.replace(/\r\n/g, "\n").split("\n")) {
    if (line.startsWith("### ")) {
      flush();
      const title = line.slice(4).trim();
      const id = slugify(title);
      topic = { id, title, audience: TOPIC_AUDIENCE[id] ?? section?.audience ?? "all", blocks: [] };
      section?.topics.push(topic);
    } else if (line.startsWith("## ")) {
      flush();
      const heading = line.slice(3).trim();
      const numbered = /^(Section \d+):\s*(.*)$/.exec(heading);
      const id = slugify(heading);
      section = {
        id,
        label: numbered ? numbered[1] : null,
        title: numbered ? numbered[2] : heading,
        audience: SECTION_AUDIENCE[id] ?? "all",
        blocks: [],
        topics: [],
      };
      topic = null;
      sections.push(section);
    } else if (line.startsWith("# ")) {
      // the document's own title; the page has its header instead
      continue;
    } else {
      buffer.push(line);
    }
  }
  flush();
  return sections;
}

export const MANUAL: Section[] = parseManual(source);

/** The manual as one reader sees it: everything for everyone, and the
 *  guide for their own role, numbered as a manual of its own. `role`
 *  null shows the whole manual as written. */
export function manualFor(role: Audience | null, sections: Section[] = MANUAL): Section[] {
  if (role === null) return sections;
  const fits = (audience: Audience) => audience === "all" || audience === role;
  const kept = sections
    .filter((section) => fits(section.audience))
    .map((section) => ({ ...section, topics: section.topics.filter((topic) => fits(topic.audience)) }));
  return renumber(kept);
}

/** The line in "How to Use This Manual" that lists all three role guides. */
const GUIDES_LINE = /^\*\*Sections \d+, \d+ and \d+:\*\*.*$/;

/** Numbers the sections left after the other roles' guides are taken
 *  out 1, 2, 3... with no gaps, so an HR admin's manual runs 1 to 5
 *  rather than 1, 2, 4, 6, 7. Topic numbers ("4.3" becomes "3.3") and
 *  the manual's references to sections ("see section 6") follow. */
function renumber(sections: Section[]): Section[] {
  const numbers = new Map<string, string>();
  sections.forEach((section) => {
    if (section.label) numbers.set(section.label.replace("Section ", ""), String(numbers.size + 1));
  });
  const renumbered = (old: string) => numbers.get(old) ?? old;
  const guide = sections.find((section) => section.audience !== "all");

  const text = (line: string) => {
    if (guide?.label && GUIDES_LINE.test(line)) {
      return `**Section ${renumbered(guide.label.replace("Section ", ""))}, ${guide.title}:** step-by-step instructions for your role.`;
    }
    return line.replace(/\b(Sections?|sections?) (\d+)/g, (_, word: string, num: string) => `${word} ${renumbered(num)}`);
  };
  const block = (b: Block): Block => {
    if (b.kind === "p") return { kind: "p", text: text(b.text) };
    if (b.kind === "table") return { kind: "table", head: b.head.map(text), rows: b.rows.map((row) => row.map(text)) };
    return { kind: b.kind, items: b.items.map(text) };
  };

  return sections.map((section) => ({
    ...section,
    label: section.label && `Section ${renumbered(section.label.replace("Section ", ""))}`,
    blocks: section.blocks.map(block),
    topics: section.topics.map((topic) => ({
      ...topic,
      title: topic.title.replace(/^(\d+)(?=\.\d)/, renumbered),
      blocks: topic.blocks.map(block),
    })),
  }));
}

function blockText(block: Block): string {
  if (block.kind === "p") return block.text;
  if (block.kind === "table") return [...block.head, ...block.rows.flat()].join(" ");
  return block.items.join(" ");
}

/** The sections, cut down to the topics that mention every word of
 *  `query`. A section whose own heading or opening matches keeps all of
 *  its topics. */
export function searchManual(sections: Section[], query: string): Section[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return sections;
  const matches = (text: string) => {
    const haystack = text.replace(/\*\*/g, "").toLowerCase();
    return words.every((word) => haystack.includes(word));
  };
  return sections.flatMap((section) => {
    const own = [section.title, ...section.blocks.map(blockText)].join(" ");
    if (matches(own)) return [section];
    const topics = section.topics.filter((topic) => matches([topic.title, ...topic.blocks.map(blockText)].join(" ")));
    return topics.length ? [{ ...section, blocks: [], topics }] : [];
  });
}

/** The topic that explains the page at `pathname`, for the ? button.
 *  The first pattern that matches wins, so the more specific come first. */
const PAGE_TOPICS: [RegExp, string][] = [
  [/^\/(applicant|hr|evaluator)\/account/, "account-settings"],
  [/^\/(applicant|hr|evaluator)\/notifications/, "notifications"],
  [/^\/applicant\/jobs/, "finding-a-job"],
  [/^\/applicant\/applications\//, "the-hiring-stages"],
  [/^\/applicant$/, "tracking-your-applications"],
  [/^\/hr\/requisitions\/new/, "creating-a-job-opening"],
  [/^\/hr\/requisitions\/[^/]+\/workflow/, "setting-the-hiring-workflow"],
  [/^\/hr\/requisitions\/[^/]+\/pre-screening-questions/, "pre-screening-questions"],
  [/^\/hr\/requisitions\/[^/]+\/final-decision-board/, "final-decision-offer-and-pre-201"],
  [/^\/hr\/applications\/[^/]+\/pre-201-package/, "final-decision-offer-and-pre-201"],
  [/^\/hr\/applications\//, "working-the-pipeline-hr-workflow"],
  [/^\/hr\/workflow-builder/, "setting-the-hiring-workflow"],
  [/^\/hr\/pre-screening-questions/, "pre-screening-questions"],
  [/^\/hr\/pipelines/, "working-the-pipeline-hr-workflow"],
  [/^\/hr\/job-openings/, "creating-a-job-opening"],
  [/^\/hr\/user-management/, "super-admin-user-management"],
  [/^\/hr$/, "the-hr-dashboard"],
  [/^\/evaluator\/interviews\//, "scoring-the-interview"],
  [/^\/evaluator$/, "your-review-queue"],
];

export function helpTopicFor(pathname: string): string | null {
  return PAGE_TOPICS.find(([pattern]) => pattern.test(pathname))?.[1] ?? null;
}

/** Every pattern's topic, so a test can check each still exists. */
export const PAGE_TOPIC_IDS: string[] = PAGE_TOPICS.map(([, id]) => id);
