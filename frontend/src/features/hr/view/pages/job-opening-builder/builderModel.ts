/** The Job Opening Builder's steps, its empty extraction, and the two
 *  built-in workflow presets. */

import type { JDExtractionResult, WorkflowPreset } from "../../../../../shared/api/pipeline";
import { makeStage, type WorkflowStageDraft } from "../../../model/workflowStages";

export const STEPS = [
  { label: "Job Title", hint: "Name the role" },
  { label: "Job Description", hint: "Upload or write it" },
  { label: "Review Details", hint: "Check every field" },
  { label: "Hiring Workflow", hint: "Set the stages" },
  { label: "Pre-Screening", hint: "Write the questions" },
  { label: "Review & Publish", hint: "Check and publish" },
];

export const WORKFLOW_STEP = 3;

export const QUESTIONS_STEP = 4;

export const PUBLISH_STEP = 5;

export const EMPTY_EXTRACTION: JDExtractionResult = {
  department: "",
  description: "",
  qualifications: "",
  requirements: "",
  additional_sections: [],
};

/** The four text fields — the ones flagged when the PDF had nothing for
 *  them. The other sections are a list and have no "missing" state. */
export type TextField = "department" | "description" | "qualifications" | "requirements";

export const TEXT_FIELDS: TextField[] = ["department", "description", "qualifications", "requirements"];

export type Source = "upload" | "manual";

/** Mirrors backend/app/api/hr/requisitions.py::_WORKFLOW_PRESETS (and
 * its round labels) — the two starting points the Workflow step offers.
 * HR adjusts the stages from there in the same editor the Workflow
 * Builder uses, and the stages themselves are what gets saved.
 *
 * reference_check/background_check are retired and in neither. */
export const WORKFLOW_PRESETS: {
  id: WorkflowPreset;
  title: string;
  description: string;
  stages: string[];
  roundLabels: Record<string, string>;
}[] = [
  {
    id: "standard",
    title: "Standard Hiring Process",
    description: "Full evaluation pipeline with pre-screening, shortlisting, examination, and three interview rounds.",
    stages: [
      "document_upload",
      "skill_matching",
      "shortlisting",
      "examination",
      "interview_round_1",
      "interview_round_2",
      "interview_round_3",
      "final_decision",
      "onboarding",
    ],
    roundLabels: {
      interview_round_1: "HR Interview",
      interview_round_2: "Department Head Interview",
      interview_round_3: "VP Interview",
    },
  },
  {
    id: "streamlined",
    title: "Streamlined Hiring Process",
    description: "Shorter pipeline for support roles: skips pre-screening, the exam, and the third interview round.",
    stages: [
      "document_upload",
      "shortlisting",
      "interview_round_1",
      "interview_round_2",
      "final_decision",
      "onboarding",
    ],
    roundLabels: {
      interview_round_1: "HR Interview",
      interview_round_2: "Department Head Interview",
    },
  },
];

export function presetStages(id: WorkflowPreset): WorkflowStageDraft[] {
  return (WORKFLOW_PRESETS.find((p) => p.id === id) ?? WORKFLOW_PRESETS[0]).stages.map(makeStage);
}

export function presetRoundLabels(id: WorkflowPreset): Record<string, string> {
  return { ...(WORKFLOW_PRESETS.find((p) => p.id === id) ?? WORKFLOW_PRESETS[0]).roundLabels };
}
