"""Resume extraction: the PDF's text (or, for a scanned PDF,
resume_text's checked transcription) is normalized by GPT-4o-mini into
ResumeExtractionResult, whatever the resume's layout."""

import logging

import openai
from langchain_openai import ChatOpenAI

from app.infra.config import settings
from app.schemas.resume import ResumeExtractionResult
from app.services.pdf_text import (
    AIExtractionFailedError,
    ExtractionNotConfiguredError,
    PdfTextExtractionError,
)
from app.services.resume_text import read_resume_text

__all__ = [
    "AIExtractionFailedError",
    "ExtractionNotConfiguredError",
    "PdfTextExtractionError",
    "extract_resume",
]

_log = logging.getLogger(__name__)

# resumes run longer than a single-page JD (multiple roles, education
# entries) but still realistically top out around 1-3 pages
_MAX_SOURCE_CHARS = 15_000

_SYSTEM_PROMPT = (
    "You extract structured fields from a resume/CV document for a "
    "university HR recruitment system. Applicants upload resumes in "
    "wildly varying layouts and formats — your job is to normalize "
    "whatever you're given into one consistent shape so downstream "
    "matching/decision-support tools can rely on a uniform structure. "
    "Return full_name, email, phone, location, linkedin_url, "
    "portfolio_url, professional_summary, education (a list of school/"
    "degree/field_of_study/start_date/end_date/honors), experience (a "
    "list of company/title/start_date/end_date/description), skills (a "
    "flat list of individual skills, not grouped phrases), and "
    "certifications. Preserve dates in whatever granularity the source "
    "gives (e.g. 'Aug 2021' or just '2021'); use 'Present' for an "
    "ongoing role. If a field can't be determined from the source text, "
    "return an empty string (or empty list, for list fields). Do not "
    "invent information that isn't present in the source text. "
    "Then, in additional_sections, capture every other section of the "
    "resume that none of those fields covers -- for example projects, "
    "awards and achievements, organizations and leadership roles, "
    "trainings and seminars, licenses and eligibility, languages, "
    "publications and research, or volunteer work. Use the resume's own "
    "heading as the title and put what sat under it in content, one item "
    "per line, keeping names, roles, dates and descriptions. Do not "
    "repeat anything already placed in another field, and do not add a "
    "section with nothing in it. Leave out personal characteristics -- "
    "age, date or place of birth, sex, civil status, religion, height, "
    "weight -- and character references' contact details: they are not "
    "qualifications, and they must not reach the people and tools that "
    "assess the applicant."
)


def extract_resume(pdf_bytes: bytes) -> ResumeExtractionResult:
    """Normalizes a resume PDF into ResumeExtractionResult with GPT-4o-mini,
    whatever its layout. Raises ExtractionNotConfiguredError without an
    OpenAI key, AIExtractionFailedError on a model failure."""
    # an image-only (scanned) PDF is transcribed here first, after a check
    # that it is a resume at all -- see services/resume_text.py
    text = read_resume_text(pdf_bytes, max_chars=_MAX_SOURCE_CHARS)

    if not settings.openai_api_key:
        _log.error(
            "AI resume extraction is unavailable: OPENAI_API_KEY is not set. "
            "See backend/.env.example."
        )
        raise ExtractionNotConfiguredError(
            "Reading your resume automatically is temporarily unavailable. You can "
            "enter your details manually and continue."
        )

    llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.openai_api_key)
    try:
        structured_llm = llm.with_structured_output(ResumeExtractionResult, method="json_schema")
        parsed = structured_llm.invoke(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Resume Document Text:\n{text}"},
            ]
        )
    except openai.OpenAIError as exc:
        raise AIExtractionFailedError(
            "Couldn't read your resume. You can fill in the fields manually."
        ) from exc

    if parsed is None:
        raise AIExtractionFailedError(
            "Couldn't read your resume. You can fill in the fields manually."
        )
    return parsed
