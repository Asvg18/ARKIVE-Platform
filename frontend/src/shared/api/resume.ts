import { openFile } from "./client";

/** Mirrors backend/app/schemas/resume.py -- the standardized shape
 * every applicant's uploaded resume gets normalized into, regardless of
 * the source file's own layout. */
export interface ResumeEducationEntry {
  school: string;
  degree: string;
  field_of_study: string;
  start_date: string;
  end_date: string;
  honors: string;
}

export interface ResumeExperienceEntry {
  company: string;
  title: string;
  start_date: string;
  end_date: string;
  description: string;
}

/** A resume section the fixed fields have no place for (projects,
 * awards, organizations...): its own heading, and what sat under it,
 * one item per line. */
export interface ResumeAdditionalSection {
  title: string;
  content: string;
}

export interface ResumeExtractionResult {
  full_name: string;
  email: string;
  phone: string;
  location: string;
  linkedin_url: string;
  portfolio_url: string;
  professional_summary: string;
  education: ResumeEducationEntry[];
  experience: ResumeExperienceEntry[];
  skills: string[];
  certifications: string[];
  additional_sections: ResumeAdditionalSection[];
}

export interface ApplicationResumeRead extends ResumeExtractionResult {
  original_filename: string;
}

export const EMPTY_RESUME_EXTRACTION: ResumeExtractionResult = {
  full_name: "",
  email: "",
  phone: "",
  location: "",
  linkedin_url: "",
  portfolio_url: "",
  professional_summary: "",
  education: [],
  experience: [],
  skills: [],
  certifications: [],
  additional_sections: [],
};

/** Opens a resume file (an authenticated, non-JSON GET) in a new tab. */
export async function openResumeFile(path: string, token: string | null): Promise<void> {
  return openFile(path, token, "Could not download the resume file.");
}
