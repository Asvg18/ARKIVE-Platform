// mirrors backend/app/domain/scorecard.py exactly -- the canonical
// Applicant Preliminary Interview Evaluation Form (MSEUF HR Dept, Doc
// Code HRD-F-APIEF, Rev 2, July 2023). hardcoded on both sides rather
// than served via an endpoint, matching this codebase's convention for
// fixed vocabulary (e.g. StageType).

export type GeneralEvaluationTier = "highly_qualified" | "qualified" | "not_qualified";

/**
 * The evaluator's own overall call, chosen on the form rather than
 * derived from the ratings.
 *
 * The tier above is arithmetic -- mean of rated items, banded. This is
 * a judgement, and the two are allowed to disagree. When they do,
 * that's information: an interviewer can rate someone solidly across
 * eleven mechanical items and still not recommend them.
 */
export type EvaluatorRecommendation =
  | "highly_recommended"
  | "recommended"
  | "not_recommended";

export const RECOMMENDATION_OPTIONS: Array<{
  value: EvaluatorRecommendation;
  label: string;
  hint: string;
}> = [
  {
    value: "highly_recommended",
    label: "Highly Recommended",
    hint: "Advance without reservation: a clear fit for the position.",
  },
  {
    value: "recommended",
    label: "Recommended",
    hint: "Suitable for the position; advance to the next round.",
  },
  {
    value: "not_recommended",
    label: "Not Recommended",
    hint: "Do not advance on the strength of this interview.",
  },
];

export interface ScorecardItem {
  code: string;
  label: string;
}

export interface ScorecardCategory {
  code: string;
  label: string;
  items: ScorecardItem[];
}

export const SCORECARD_CATEGORIES: ScorecardCategory[] = [
  {
    code: "A",
    label: "Personal Background",
    items: [
      { code: "A1", label: "Ability to provide personal information" },
      { code: "A2", label: "Personal background fitted to the job applied for" },
    ],
  },
  {
    code: "B",
    label: "Educational Qualifications",
    items: [
      { code: "B1", label: "Educational background appropriate to the vacancy to be fitted" },
      {
        code: "B2",
        label: "Confident that his/her educational background will meet the needs of the job applied for",
      },
    ],
  },
  {
    code: "C",
    label: "Work Background",
    items: [
      { code: "C1", label: "Previous work background" },
      { code: "C2", label: "Reasons for leaving previous job" },
      { code: "C3", label: "Work references/professional references" },
    ],
  },
  {
    code: "D",
    label: "Job Expectations",
    items: [
      { code: "D1", label: "Knowledge and reasons for applying MSEUF" },
      { code: "D2", label: "Expectations of job applied for" },
      { code: "D3", label: "Salary or wage expectations" },
      { code: "D4", label: "Career development and leadership potential" },
    ],
  },
];

export const SCORECARD_ITEM_CODES: string[] = SCORECARD_CATEGORIES.flatMap((c) =>
  c.items.map((i) => i.code)
);

export const RATING_SCALE_LEGEND: Array<[number, string]> = [
  [5, "Outstanding"],
  [4, "Very Good"],
  [3, "Good"],
  [2, "Improvement Needed"],
  [1, "Unsatisfactory"],
];

export const TIER_COPY: Record<GeneralEvaluationTier, { label: string; description: string }> = {
  highly_qualified: {
    label: "Highly Qualified",
    description:
      "Candidate provides a thorough response to the questions. Candidate demonstrates a thorough understanding of the issues at hand that is more to substantially more than the job requires. Responses are well thought-out and well presented. Overall, candidate's response is complete, addresses all aspects of the questions and does not require probing.",
  },
  qualified: {
    label: "Qualified",
    description:
      "Candidate provides an acceptable response to the questions. Candidate's understanding of the issues at hand is equal to or slightly less than what the job requires. The responses may not be as complete or thorough as the highly qualified candidate's responses. Overall, candidate's response is complete, addresses the question and any probing required is minimal.",
  },
  not_qualified: {
    label: "Not Qualified",
    description:
      "Candidate fails to provide an acceptable response to the questions. Candidate's responses do not convey the level of experience/expertise required in the position. Candidate's responses may be vague or incomplete. Overall, candidate fails to provide experience/expertise demonstrative of the requirements of the position.",
  },
};
