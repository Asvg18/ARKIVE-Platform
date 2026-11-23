/** The résumé as the review form edits it, and the conversions to and
 *  from the extracted profile. */

import {
  EMPTY_RESUME_EXTRACTION,
  type ResumeAdditionalSection,
  type ResumeEducationEntry,
  type ResumeExperienceEntry,
  type ResumeExtractionResult,
} from "../../../../../shared/api/resume";

// Editing skills/certifications as free-flowing comma-separated text (kept
// in its own state, converted to string[] only on submit) is deliberately
// simpler than a tag-input widget — and avoids the cursor-jump you'd get
// from deriving the input's value from the array on every keystroke (a
// trailing ", " the user just typed would vanish on re-render before they
// can type the next skill).
export interface EditableResume {
  full_name: string;
  email: string;
  phone: string;
  location: string;
  linkedin_url: string;
  portfolio_url: string;
  professional_summary: string;
  education: ResumeEducationEntry[];
  experience: ResumeExperienceEntry[];
  skillsText: string;
  certificationsText: string;
  additional_sections: ResumeAdditionalSection[];
}

export function toEditable(result: ResumeExtractionResult): EditableResume {
  return {
    full_name: result.full_name,
    email: result.email,
    phone: result.phone,
    location: result.location,
    linkedin_url: result.linkedin_url,
    portfolio_url: result.portfolio_url,
    professional_summary: result.professional_summary,
    education: result.education,
    experience: result.experience,
    skillsText: result.skills.join(", "),
    certificationsText: result.certifications.join(", "),
    additional_sections: result.additional_sections ?? [],
  };
}

export function toResult(editable: EditableResume): ResumeExtractionResult {
  return {
    full_name: editable.full_name,
    email: editable.email,
    phone: editable.phone,
    location: editable.location,
    linkedin_url: editable.linkedin_url,
    portfolio_url: editable.portfolio_url,
    professional_summary: editable.professional_summary,
    education: editable.education,
    experience: editable.experience,
    skills: editable.skillsText.split(",").map((s) => s.trim()).filter(Boolean),
    certifications: editable.certificationsText.split(",").map((s) => s.trim()).filter(Boolean),
    // A section added and then left blank is dropped rather than sent
    // as an empty heading.
    additional_sections: editable.additional_sections
      .map((section) => ({ title: section.title.trim(), content: section.content.trim() }))
      .filter((section) => section.title || section.content),
  };
}

export const EMPTY_EDITABLE: EditableResume = toEditable(EMPTY_RESUME_EXTRACTION);
