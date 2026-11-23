"""How text is made comparable before scoring and retrieval: one
tokenizer for both sides, and the text a resume or a job is scored on.
"""

import re

from app.models.application_resume import ApplicationResume
from app.models.job_requisition import JobRequisition


# Degree titles folded onto one spelling before keyword scoring, on the
# requirement and the resume alike, so "MS in Computer Science" matches
# "Master's degree in Computer Science". "MS"/"BS" fold only before
# "in"/"of" ("MS Office" stays). Compound titles (BSCS) must come first.
_DEGREE_FORMS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), replacement)
    for pattern, replacement in (
        (r"\bbscs\b", "bachelor science computer science"),
        (r"\bbsit\b", "bachelor science information technology"),
        (r"\bbsis\b", "bachelor science information systems"),
        (r"\bbsed\b", "bachelor science education"),
        (r"\bbeed\b", "bachelor elementary education"),
        (r"\bmscs\b", "master science computer science"),
        (r"\bmsit\b", "master science information technology"),
        (r"\bm\.?a\.?ed\.?\b|\bm\.?ed\.?(?=\s|,|$)", "master education"),
        (r"\bmba\b", "master business administration"),
        (r"\bph\.?\s?d\b\.?|\bdoctor(?:al|ate)?\s+(?:degree\s+)?(?:of|in)\s+philosophy\b|\bdoctor(?:al|ate)\b", "doctorate"),
        (r"\bmasters?\b|\bmaster['’]s\b", "master"),
        (r"\bm\.?\s?sc?\.?(?=\s+(?:in|of)\b)", "master science"),
        (r"\bm\.a\.(?=\s)", "master arts"),
        (r"\bbachelors?\b|\bbachelor['’]s\b", "bachelor"),
        (r"\bb\.?\s?sc?\.?(?=\s+(?:in|of)\b)", "bachelor science"),
        (r"\b(?:b\.?a|a\.?b)\.?(?=\s+(?:in|of)\b)", "bachelor arts"),
        (r"\bcs\b", "computer science"),
        (r"\bi\.t\.", "information technology"),
    )
)


# leading bullets and "1." / "2)" markers; "5+ years" is left alone
_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


_POSSESSIVE_RE = re.compile(r"['’]s\b")


def _stem(token: str) -> str:
    """A plural folded onto its singular -- "skills"/"skill",
    "systems"/"system" -- and nothing cleverer. Leaves "-ss", "-us" and
    "-is" endings alone (class, campus, analysis), and short words, where
    a trailing s is usually the word."""
    if len(token) > 4 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def _tokenize(text: str) -> list[str]:
    """What BM25 counts, on both sides: lower case, degree titles in one
    spelling (_DEGREE_FORMS), possessives dropped, plurals singular."""
    text = text.lower()
    for pattern, replacement in _DEGREE_FORMS:
        text = pattern.sub(replacement, text)
    text = _POSSESSIVE_RE.sub("", text)
    return [_stem(token) for token in re.findall(r"[a-z0-9]+", text)]


def _requisition_corpus_text(requisition: JobRequisition) -> str:
    parts = [
        requisition.title,
        requisition.department,
        requisition.description or "",
        requisition.qualifications or "",
        requisition.requirements or "",
    ]
    return "\n".join(p for p in parts if p)


def _resume_scoring_text(resume: ApplicationResume) -> str:
    """What both halves of the match score read: the resume fields the
    applicant reviewed and submitted, not the raw text pypdf pulled out of
    the PDF.

    So corrections made on the review step count, and a two-column layout
    arrives in order. The same content the analysis retrieves over, plus
    the professional summary, written once per section so BM25 does not
    count repeated headings. Leaves out the contact block and dates;
    school names stay. Falls back to the raw text only when every field
    is blank."""
    lines: list[str] = []
    summary = (resume.professional_summary or "").strip()
    if summary:
        lines.append(summary)
    for entry in resume.experience or []:
        title = (entry.get("title") or "").strip()
        company = (entry.get("company") or "").strip()
        description = (entry.get("description") or "").strip()
        role = f"{title} at {company}" if title and company else title or company
        line = f"{role}: {description}" if role and description else role or description
        if line:
            lines.append(line)
    for entry in resume.education or []:
        degree = (entry.get("degree") or "").strip()
        field = (entry.get("field_of_study") or "").strip()
        degree_line = f"{degree} in {field}" if degree and field else degree or field
        school = (entry.get("school") or "").strip()
        honors = (entry.get("honors") or "").strip()
        line = ", ".join(part for part in (degree_line, school, honors) if part)
        if line:
            lines.append(line)
    skills = [skill.strip() for skill in resume.skills or [] if skill and skill.strip()]
    if skills:
        lines.append("Skills: " + ", ".join(skills))
    certifications = [cert.strip() for cert in resume.certifications or [] if cert and cert.strip()]
    if certifications:
        lines.append("Certifications: " + ", ".join(certifications))
    for section in resume.additional_sections or []:
        title = (section.get("title") or "").strip()
        content = (section.get("content") or "").strip()
        if content:
            lines.append(f"{title}: {content}" if title else content)
    return "\n".join(lines) or (resume.raw_extracted_text or "")
