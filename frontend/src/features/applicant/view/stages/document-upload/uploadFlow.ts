/** The upload flow's two steps and what its progress bars tick off while
 *  the applicant waits. */

import type { ReadingStep } from "../../../../../shared/ui/ReadingProgress";

export const STEPS = ["Upload Resume", "Review & Submit"];

// What the applicant waits through, named, with an estimated percentage.
// Reading is one model call; the
// submit also scores the resume against the job, so it runs longer.
// What reading ticks off, in the order a resume is usually laid out.
// Spaced so most tick inside the expected
// time; whatever is left ticks when the reading actually comes back.
export const READ_STEPS: ReadingStep[] = [
  { label: "Contact details", until: 15 },
  { label: "Education", until: 35 },
  { label: "Work experience", until: 55 },
  { label: "Skills and certifications", until: 75 },
];

// Submitting saves the application, then scores it against the job. The
// match only ticks when the real answer comes back.
export const SUBMIT_STEPS: ReadingStep[] = [
  { label: "Saving your application", until: 12 },
  { label: "Matching your skills to the job", until: 100 },
];

export const READ_EXPECTED_MS = 20_000;

export const SUBMIT_EXPECTED_MS = 25_000;

// How long a finished bar holds at 100% before the screen moves on, so
// the applicant sees it complete rather than vanish.
export const DONE_PAUSE_MS = 500;
