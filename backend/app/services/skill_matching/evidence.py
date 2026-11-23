"""The units a resume and a job are compared in: the job's requirement
lines, the resume's evidence chunks (with their sections), and the role
context the judging agents are given.
"""

import re

from app.models.application_resume import ApplicationResume
from app.models.job_requisition import JobRequisition

from .text import _BULLET_PREFIX_RE, _requisition_corpus_text


def _target_requirements(requisition: JobRequisition) -> tuple[list[str], bool]:
    """The requirement lines a job is screened against, and whether they
    are real lines (True) or the posting's prose standing in for them
    (False, a job with no qualifications/requirements filled in).

    Shared by the arithmetic half and the Context Router, so the
    requirements the score is averaged over and the ones the Scoring
    Agent gives verdicts on are the same strings."""
    requirements = _chunk_jd_requirements(requisition)
    if requirements:
        return requirements, True
    return [_requisition_corpus_text(requisition)[:2000]], False


def _resume_units(resume: ApplicationResume) -> list[str]:
    """What the arithmetic half compares each requirement with: the
    professional summary plus the same evidence units retrieval ranks,
    from the reviewed form; the PDF's paragraphs only when the form is
    blank."""
    summary = (resume.professional_summary or "").strip()
    units = ([summary] if summary else []) + _chunk_resume_evidence(resume)
    return units or _fallback_resume_chunks(resume)


def _chunk_jd_requirements(requisition: JobRequisition) -> list[str]:
    """Splits qualifications/requirements into one chunk per line (the
    extraction prompt asks for one item per line). Bullets and numbering
    are stripped, since HR can hand-edit the text."""
    raw = "\n".join(filter(None, [requisition.qualifications, requisition.requirements]))
    chunks = []
    for line in raw.splitlines():
        cleaned = _BULLET_PREFIX_RE.sub("", line).strip()
        if cleaned:
            chunks.append(cleaned)
    return chunks


def _labelled_resume_evidence(resume: ApplicationResume) -> list[tuple[str, str]]:
    """(section, chunk) for every evidence chunk -- section one of
    "experience", "education", "skills", "credential" or "other". The
    label never reaches retrieval or a model; it is what lets
    _ensure_section_evidence hand a degree requirement the education
    entries without guessing from the chunk's wording."""
    chunks: list[tuple[str, str]] = []
    for entry in resume.experience:
        title = entry.get("title", "")
        company = entry.get("company", "")
        description = entry.get("description", "")
        text = f"{title} at {company}: {description}".strip(": ").strip()
        if text:
            chunks.append(("experience", text))
    for entry in resume.education:
        degree = entry.get("degree", "")
        field = entry.get("field_of_study", "")
        school = entry.get("school", "")
        degree_line = f"{degree} in {field}".strip() if degree or field else ""
        text = ", ".join(part for part in (degree_line, school) if part)
        if text:
            chunks.append(("education", text))
    for i in range(0, len(resume.skills), 4):
        group = resume.skills[i : i + 4]
        if group:
            chunks.append(("skills", "Skills: " + ", ".join(group)))
    for cert in resume.certifications:
        if cert:
            chunks.append(("credential", f"Certification: {cert}"))
    # One chunk per line, headed by its section, so a project or an award
    # can be retrieved as evidence the same way one experience entry is.
    # The match score reads these sections too, through
    # _resume_scoring_text. A licence or eligibility section counts as a
    # credential, for the same reason a certification does.
    for section in resume.additional_sections or []:
        title = (section.get("title") or "").strip()
        label = "credential" if _CREDENTIAL_SECTION_RE.search(title) else "other"
        for line in (section.get("content") or "").splitlines():
            cleaned = _BULLET_PREFIX_RE.sub("", line).strip()
            if cleaned:
                chunks.append((label, f"{title}: {cleaned}" if title else cleaned))
    return chunks


def _chunk_resume_evidence(resume: ApplicationResume) -> list[str]:
    """The retrieval units: built from the resume's structured fields
    (experience, education, skills, certifications, additional
    sections), not the raw text."""
    return [text for _, text in _labelled_resume_evidence(resume)]


# Which resume section a requirement is about, when that can be told
# from its words: a degree requirement is answered by the education
# entries, a licence or certification requirement by the credentials, a
# skill or tool requirement by the skills list.
# Anything else is left to retrieval alone.
_EDUCATION_REQUIREMENT_RE = re.compile(
    r"\b(degree|bachelor|master|doctor|doctorate|ph\.?\s?d|graduate|diploma|units?\s+in|"
    r"bscs|bsit|mscs|educational\s+(?:attainment|background))(?:['’]?s)?\b",
    re.IGNORECASE,
)
_CREDENTIAL_REQUIREMENT_RE = re.compile(
    r"\b(licen[cs](?:e[ds]?|ure)|certifi(?:ed|cate|cation)s?|eligib(?:le|ility)|board\s+exam|let\b|prc\b|passer)",
    re.IGNORECASE,
)
_CREDENTIAL_SECTION_RE = re.compile(r"licen|certif|eligib|board|exam", re.IGNORECASE)
_SKILL_REQUIREMENT_RE = re.compile(
    r"\b(skills?|proficien\w*|programming|languages?|tools?|software|frameworks?|"
    r"technolog\w*|platforms?|stack)\b",
    re.IGNORECASE,
)


def _requirement_sections(requirement: str) -> set[str]:
    sections = set()
    if _EDUCATION_REQUIREMENT_RE.search(requirement):
        sections.add("education")
    if _CREDENTIAL_REQUIREMENT_RE.search(requirement):
        sections.add("credential")
    if _SKILL_REQUIREMENT_RE.search(requirement):
        sections.add("skills")
    return sections


def _names_listed_skill(requirement: str, skills_chunk: str) -> bool:
    """Whether a requirement names one of the skills in a "Skills: a, b"
    chunk, as a whole word -- "C++" in "Python, Java, and C++", but not
    "Java" in "JavaScript"."""
    listed = skills_chunk.split(":", 1)[-1]
    lowered = requirement.lower()
    return any(
        re.search(rf"(?<![\w+#]){re.escape(skill)}(?![\w+#])", lowered)
        for skill in (s.strip().lower() for s in listed.split(","))
        if len(skill) > 1
    )


#: The most section entries added to one requirement's evidence. A
#: resume rarely lists more than three degrees, and the cap keeps a
#: long certification list from crowding out what retrieval found.
_SECTION_EVIDENCE_LIMIT = 3


def _ensure_section_evidence(
    evidence_by_requirement: dict[str, list[str]],
    chunks: list[str],
    sections: list[str],
) -> dict[str, list[str]]:
    """Adds the education entries to every degree requirement's evidence,
    the credentials to every licence/certification one, and the whole
    skills list, as one item, to every skill or tool requirement (and to
    any requirement naming a skill on it), when retrieval did not already
    rank them in.

    Retrieval ranks by word likeness and can miss the real degree entry,
    and a degree verdict is only as good as the degrees it is shown.
    Appended after what retrieval found, never in place of it.

    `sections` is aligned with `chunks` (see _labelled_resume_evidence);
    a length mismatch -- the raw-text fallback corpus, which has no
    sections -- leaves the evidence as retrieval returned it."""
    if len(sections) != len(chunks):
        return evidence_by_requirement
    # one item, not the groups it is chunked into for retrieval: "Python,
    # Java" in one group and "C++" in the next reads as a list without C++
    skills = [chunk for chunk, label in zip(chunks, sections) if label == "skills"]
    whole_skills = (
        "Skills: " + ", ".join(chunk.split(":", 1)[-1].strip() for chunk in skills) if skills else ""
    )
    completed: dict[str, list[str]] = {}
    for requirement, evidence in evidence_by_requirement.items():
        wanted = _requirement_sections(requirement)
        extra: list[str] = []
        for section in ("education", "credential"):
            if section in wanted:
                extra += [
                    chunk
                    for chunk, label in zip(chunks, sections)
                    if label == section and chunk not in evidence
                ][:_SECTION_EVIDENCE_LIMIT]
        if whole_skills and whole_skills not in evidence and (
            "skills" in wanted or any(_names_listed_skill(requirement, chunk) for chunk in skills)
        ):
            extra.append(whole_skills)
        completed[requirement] = [*evidence, *extra]
    return completed


def _role_context(requisition) -> str:
    """What a judging agent is told about the role, so it can tell an
    equivalent qualification from a merely similar one -- the same
    Master of Education major in Computer Science Teaching meets a
    Computer Science teaching post and only partly meets a software
    engineering one. Title, department, and the opening of the job
    description, which is where a posting says what the work is."""
    if requisition is None:
        return ""
    lines = [f"Job Title: {requisition.title}", f"Department: {requisition.department}"]
    description = " ".join((requisition.description or "").split())
    if description:
        lines.append(f"About the role: {description[:600]}{'…' if len(description) > 600 else ''}")
    return "\n".join(lines)


def _fallback_resume_chunks(resume: ApplicationResume) -> list[str]:
    """Only reached if a resume has zero structured entries (applicant
    left every review-step field blank) -- falls back to raw text split
    into paragraphs, so retrieval never runs on an empty corpus."""
    raw = resume.raw_extracted_text or ""
    paragraphs = [p.strip() for p in raw.split("\n\n") if p.strip()]
    return paragraphs or ([raw.strip()] if raw.strip() else [])
