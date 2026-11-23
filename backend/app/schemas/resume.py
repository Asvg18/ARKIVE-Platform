"""The standardized resume shape every upload is normalized into
(services/resume_extraction.py); the agents read this, not raw text."""

from pydantic import BaseModel, Field


class ResumeEducationEntry(BaseModel):
    school: str
    degree: str
    field_of_study: str
    # free text, not `date` -- resumes give dates in wildly different
    # formats ("2019", "Aug 2019", "Fall 2019") and "Present" isn't a
    # valid date at all
    start_date: str
    end_date: str
    honors: str


class ResumeExperienceEntry(BaseModel):
    company: str
    title: str
    start_date: str
    end_date: str
    description: str


class ResumeAdditionalSection(BaseModel):
    """Anything on the résumé the fixed fields above have no place for --
    projects, awards, organizations, seminars, licenses, languages. The
    résumé's own heading and what sat under it, one item per line.

    Free-form on purpose (revisions round 2): résumés vary too much in
    what they include to enumerate every section as its own field, and a
    fixed list would just move where the information gets dropped."""

    title: str
    content: str


class ResumeExtractionResult(BaseModel):
    """GPT-4o-mini structured output -- same "empty for anything not
    determinable, never invent" contract as JDExtractionResult, so the
    applicant always reviews/edits before this is submitted and
    persisted."""

    full_name: str
    email: str
    phone: str
    location: str
    linkedin_url: str
    portfolio_url: str
    professional_summary: str
    education: list[ResumeEducationEntry]
    experience: list[ResumeExperienceEntry]
    skills: list[str]
    certifications: list[str]
    # default_factory, not a default -- OpenAI's strict schema still marks
    # it required (so the model always answers it), while a submission
    # or stored row from before this field existed reads as "none".
    additional_sections: list[ResumeAdditionalSection] = Field(default_factory=list)


class ResumeImageReading(BaseModel):
    """GPT-4o-mini's reading of a PDF that is only page images (a scanned
    or photographed résumé) -- see services/resume_text.py. The verdict
    comes before the transcription: `text` is only filled in when
    `is_resume` is true."""

    is_resume: bool
    reason: str
    text: str


class ApplicationResumeRead(ResumeExtractionResult):
    """The persisted, standardized resume attached to an application — the
    applicant's reviewed/edited copy of the extraction result, plus the
    original filename. Shared read shape across the applicant's own view,
    the HR Candidate Profile, and the Evaluator's interview detail."""

    original_filename: str
