import type { JobDescriptionSection } from "../../../shared/api/pipeline";

/** Trimmed, with any section left with neither a heading nor anything
 *  under it dropped — what the server stores (job_descriptions.
 *  clean_sections), so "changed" here means changed there. */
export function cleanSections(sections: JobDescriptionSection[]): JobDescriptionSection[] {
  return sections
    .map((s) => ({ title: s.title.trim(), content: s.content.trim() }))
    .filter((s) => s.title || s.content);
}

export function sameSections(a: JobDescriptionSection[], b: JobDescriptionSection[]): boolean {
  const left = cleanSections(a);
  const right = cleanSections(b);
  return left.length === right.length && left.every((s, i) => s.title === right[i].title && s.content === right[i].content);
}
