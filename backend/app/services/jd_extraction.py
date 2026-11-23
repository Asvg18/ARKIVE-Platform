"""Job description extraction (extract_job_description)."""

import logging

import openai
from langchain_openai import ChatOpenAI

from app.infra.config import settings
from app.domain.jd_rules import NotAJobDescriptionError, yields_nothing_usable
from app.schemas.pipeline import JDExtractionCandidate, JDExtractionResult
from app.services.pdf_text import (
    AIExtractionFailedError,
    ExtractionNotConfiguredError,
    PdfTextExtractionError,
)
from app.services.jd_text import read_job_description_text

__all__ = [
    "AIExtractionFailedError",
    "ExtractionNotConfiguredError",
    "NotAJobDescriptionError",
    "PdfTextExtractionError",
    "extract_job_description",
]


_log = logging.getLogger(__name__)

# a JD is never realistically longer than this -- caps the request cost
# if someone uploads something malformed/oversized
_MAX_SOURCE_CHARS = 12_000

_SYSTEM_PROMPT = (
    "You extract structured fields from a job description document for a "
    "university HR system. Given a job title and the raw text of a job "
    "description PDF, return department, description, qualifications, and "
    "requirements. `department` is the office/department the role belongs "
    "to. `description` is a clean overview paragraph of the role — the job "
    "title is already displayed separately by the UI, so never restate it "
    "as a heading or opening line; start directly with what the role does. "
    "`qualifications` is required education/experience, one item per line. "
    "`requirements` is required skills/competencies, one item per line. "
    "If a field can't be determined from the source text, return an empty "
    "string for it. Do not invent information that isn't present in the "
    "source text. "
    "Then, in `additional_sections`, capture every other part of the "
    "document that none of those fields covers -- for example duties and "
    "responsibilities, salary or compensation, benefits, employment status, "
    "working hours, place of assignment, documents to submit, or how to "
    "apply. Use the document's own heading as the title and put what sat "
    "under it in content, one item per line. Do not repeat anything "
    "already placed in another field, and do not add a section with "
    "nothing in it.\n\n"
    "FIRST, judge what the document actually is. Set `is_job_description` "
    "true only if this document is genuinely a job posting or position "
    "description — it advertises or defines a specific role someone could "
    "be hired into. Set it false for anything else, however professional "
    "it looks: lecture notes, course handouts, syllabi, essays, reports, "
    "policies, memos, forms, resumes/CVs, certificates, minutes, or "
    "marketing material. A document that merely *mentions* jobs, careers "
    "or workplace topics is not a job description. When it is false, set "
    "`document_kind` to a short plain description of what it appears to "
    "be instead (e.g. 'a lecture handout on professional English', 'a "
    "resume', 'a university policy memo') and `reason` to one sentence "
    "explaining how you can tell. When it is true, leave `reason` empty "
    "and set `document_kind` to 'job description'."
)

def extract_job_description(job_title: str, pdf_bytes: bytes) -> JDExtractionResult:
    """Structures a job description PDF with GPT-4o-mini into department,
    description, qualifications and requirements, plus titled sections for
    anything else. A scanned PDF is first checked and transcribed by
    jd_text. Raises NotAJobDescriptionError when the model says it is not a
    job description, or when nothing usable came out (yields_nothing_usable);
    ExtractionNotConfiguredError / AIExtractionFailedError otherwise."""
    text = read_job_description_text(pdf_bytes, max_chars=_MAX_SOURCE_CHARS)

    if not settings.openai_api_key:
        _log.error(
            "AI job-description extraction is unavailable: OPENAI_API_KEY is not set. "
            "See backend/.env.example."
        )
        raise ExtractionNotConfiguredError(
            "Reading the job description automatically is temporarily unavailable. "
            "You can fill in the fields manually and continue."
        )

    llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.openai_api_key)
    try:
        structured_llm = llm.with_structured_output(JDExtractionCandidate, method="json_schema")
        parsed = structured_llm.invoke(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Job Title: {job_title}\n\nJob Description Document Text:\n{text}",
                },
            ]
        )
    except openai.OpenAIError as exc:
        raise AIExtractionFailedError(
            "Couldn't read the document. You can fill in the fields manually."
        ) from exc

    if parsed is None:
        raise AIExtractionFailedError(
            "Couldn't read the document. You can fill in the fields manually."
        )

    if not parsed.is_job_description:
        raise NotAJobDescriptionError(parsed.document_kind, parsed.reason)
    if yields_nothing_usable(parsed):
        raise NotAJobDescriptionError(
            parsed.document_kind or "a document with no role details in it",
            "Nothing that describes a role (no overview, no qualifications, no requirements) could be read out of it.",
        )

    # verdict stays server-side -- client only gets the fields it asked
    # for, nothing it could choose to ignore
    return JDExtractionResult(
        department=parsed.department,
        description=parsed.description,
        qualifications=parsed.qualifications,
        requirements=parsed.requirements,
        additional_sections=[
            section
            for section in parsed.additional_sections
            if section.title.strip() or section.content.strip()
        ],
    )
