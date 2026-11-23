/** The Candidate Profile's tabs, in order, and their labels. */
export const TABS = [
  "synthesis",
  "pre-screening",
  "shortlisting",
  "examinations",
  "interviews",
  "documents",
] as const;

export type Tab = (typeof TABS)[number];

export const DEFAULT_TAB: Tab = "synthesis";

export const TAB_LABELS: Record<Tab, string> = {
  synthesis: "Synthesis",
  "pre-screening": "Pre-Screening",
  shortlisting: "Shortlisting",
  examinations: "Examinations",
  interviews: "Interviews",
  documents: "Documents",
};

export const TABLIST_ID = "candidate-tabs";
