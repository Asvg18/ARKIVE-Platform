"""Job-description versions: recording them, replacing the one in force,
and saying which applicants were scored against which.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, NamedTuple, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.candidate_application import CandidateApplication
from app.models.enums import StageType
from app.models.job_description_version import JobDescriptionVersion
from app.models.job_requisition import JobRequisition
from app.models.stage_instance import StageInstance
from app.services.file_storage import job_description_stored_path, resolve_job_description_path

__all__ = [
    "NothingChangedError",
    "SectionInput",
    "StoredUpload",
    "UnknownUploadError",
    "clean_sections",
    "current_version",
    "current_version_number",
    "ensure_initial_versions",
    "record_initial_version",
    "replace_job_description",
    "resolve_upload",
    "scored_counts",
    "version_file_paths",
]


class UnknownUploadError(ValueError):
    """The upload id doesn't name a saved PDF, or names one another
    version already uses."""


class NothingChangedError(ValueError):
    """A replacement with the same text and no new document."""


def _clean(text: str | None) -> str | None:
    text = (text or "").strip()
    return text or None


class SectionInput(Protocol):
    """One additional section as a request carries it --
    schemas.job_description.JobDescriptionSection satisfies this. A
    Protocol so this module needn't import the API's schemas."""

    title: str
    content: str


def clean_sections(sections: Iterable[SectionInput] | None) -> list[dict[str, str]]:
    """Trimmed, as stored ([{title, content}]), with any section left
    with neither a heading nor anything under it dropped -- a blank box
    HR added and never filled is not part of the job description."""
    cleaned = []
    for section in sections or []:
        title, content = section.title.strip(), section.content.strip()
        if title or content:
            cleaned.append({"title": title, "content": content})
    return cleaned


def current_version(db: Session, requisition_id: int) -> JobDescriptionVersion | None:
    return db.scalar(
        select(JobDescriptionVersion)
        .where(
            JobDescriptionVersion.requisition_id == requisition_id,
            JobDescriptionVersion.replaced_at.is_(None),
        )
        .order_by(JobDescriptionVersion.version.desc())
        .limit(1)
    )


def current_version_number(db: Session, requisition_id: int) -> int:
    """The version a score computed right now is measured against. A job
    with no rows yet (one created outside the API, like the seed script's)
    is on its original text, which is version 1."""
    latest = db.scalar(
        select(func.max(JobDescriptionVersion.version)).where(
            JobDescriptionVersion.requisition_id == requisition_id
        )
    )
    return latest or 1


class StoredUpload(NamedTuple):
    stored_path: str
    size: int


def resolve_upload(db: Session, upload_id: str | None) -> StoredUpload | None:
    """The saved PDF an upload id names, or None when there is no id.

    Raises UnknownUploadError before anything is written, so a caller can
    check the id first and refuse the request with nothing to undo."""
    if not upload_id:
        return None
    stored_path = job_description_stored_path(upload_id)
    if stored_path is None:
        raise UnknownUploadError("That uploaded document could not be found. Upload it again.")
    already_used = db.scalar(
        select(JobDescriptionVersion.id).where(JobDescriptionVersion.stored_path == stored_path)
    )
    if already_used is not None:
        raise UnknownUploadError("That document is already attached to a job description.")
    return StoredUpload(stored_path, resolve_job_description_path(stored_path).stat().st_size)


def record_initial_version(
    db: Session,
    requisition: JobRequisition,
    *,
    uploaded_by: int | None,
    upload: StoredUpload | None = None,
) -> JobDescriptionVersion:
    """Version 1, from the text the job was created with, and the PDF it
    was read from if there was one. Flushes, does not
    commit -- the caller creates the job and this in one transaction, and
    resolves the upload (resolve_upload) before creating either."""
    version = JobDescriptionVersion(
        requisition_id=requisition.id,
        version=1,
        original_filename=requisition.jd_filename,
        stored_path=upload.stored_path if upload else None,
        file_size=upload.size if upload else None,
        description=requisition.description,
        qualifications=requisition.qualifications,
        requirements=requisition.requirements,
        additional_sections=list(requisition.additional_sections or []),
        uploaded_by=uploaded_by,
    )
    db.add(version)
    db.flush()
    return version


def ensure_initial_versions(db: Session) -> None:
    """Records version 1 for any job that has no versions yet.

    Covers jobs created outside the API (seed scripts, tests).
    Idempotent. Flushes, does not commit."""
    missing = db.scalars(
        select(JobRequisition).where(
            ~select(JobDescriptionVersion.id)
            .where(JobDescriptionVersion.requisition_id == JobRequisition.id)
            .exists()
        )
    ).all()
    for requisition in missing:
        db.add(
            JobDescriptionVersion(
                requisition_id=requisition.id,
                version=1,
                original_filename=requisition.jd_filename,
                description=requisition.description,
                qualifications=requisition.qualifications,
                requirements=requisition.requirements,
                additional_sections=list(requisition.additional_sections or []),
                uploaded_by=requisition.created_by,
                created_at=requisition.created_at,
            )
        )
    if missing:
        db.flush()


def replace_job_description(
    db: Session,
    requisition: JobRequisition,
    *,
    replaced_by: int,
    description: str | None,
    qualifications: str | None,
    requirements: str | None,
    upload_id: str | None,
    original_filename: str | None,
    change_note: str | None,
    additional_sections: Iterable[SectionInput] | None = None,
) -> JobDescriptionVersion:
    """Puts a new version in force: the requisition's text columns take the
    new text, the previous version is stamped `replaced_at`, and the cached
    embedding is cleared so the *next* applicant is measured against the
    new text. Nobody already scored is re-scored: their stored result
    keeps its numbers and its version (SkillMatchResult.jd_version), since
    HR may have acted on them. Does not commit.

    `additional_sections` of None keeps the sections in force; an empty
    list clears them.

    Raises NothingChangedError for a replacement identical to the current
    text with no new document."""
    ensure_initial_versions(db)
    previous = current_version(db, requisition.id)

    description, qualifications, requirements = (
        _clean(description),
        _clean(qualifications),
        _clean(requirements),
    )
    current_sections = list(requisition.additional_sections or [])
    sections = current_sections if additional_sections is None else clean_sections(additional_sections)
    scored_text_same = (
        description == _clean(requisition.description)
        and qualifications == _clean(requisition.qualifications)
        and requirements == _clean(requisition.requirements)
    )
    same_text = scored_text_same and sections == current_sections
    if same_text and not upload_id:
        raise NothingChangedError(
            "The new text is the same as the current job description, so there is nothing to replace."
        )

    upload = resolve_upload(db, upload_id)
    now = datetime.now(timezone.utc)
    if previous is not None:
        previous.replaced_at = now

    version = JobDescriptionVersion(
        requisition_id=requisition.id,
        version=current_version_number(db, requisition.id) + 1,
        original_filename=original_filename if upload else None,
        stored_path=upload.stored_path if upload else None,
        file_size=upload.size if upload else None,
        description=description,
        qualifications=qualifications,
        requirements=requirements,
        additional_sections=sections,
        uploaded_by=replaced_by,
        change_note=_clean(change_note),
    )
    db.add(version)

    requisition.description = description
    requisition.qualifications = qualifications
    requisition.requirements = requirements
    requisition.additional_sections = sections
    requisition.jd_filename = version.original_filename
    # clear the cached embedding of the old text; additional sections are
    # not part of the match, so editing only them keeps it
    if not scored_text_same or upload_id:
        requisition.embedding = None

    db.flush()
    return version


def scored_counts(db: Session, requisition_ids: list[int]) -> Counter[tuple[int, int]]:
    """How many applicants have a stored match score, by (job, version).

    Read from the skill_matching stage payloads; no jd_version means
    version 1."""
    counts: Counter[tuple[int, int]] = Counter()
    if not requisition_ids:
        return counts
    rows = db.execute(
        select(CandidateApplication.requisition_id, StageInstance.payload)
        .join(StageInstance, StageInstance.application_id == CandidateApplication.id)
        .where(
            CandidateApplication.requisition_id.in_(requisition_ids),
            StageInstance.stage_type == StageType.skill_matching,
        )
    )
    for requisition_id, payload in rows:
        if not payload or payload.get("match_score") is None:
            continue
        counts[(requisition_id, payload.get("jd_version") or 1)] += 1
    return counts


def version_file_paths(db: Session, requisition_id: int) -> list[Path]:
    """On-disk paths of every stored document for this job -- for the
    delete cascade, which unlinks them after its commit lands."""
    return [
        resolve_job_description_path(p)
        for p in db.scalars(
            select(JobDescriptionVersion.stored_path).where(
                JobDescriptionVersion.requisition_id == requisition_id,
                JobDescriptionVersion.stored_path.is_not(None),
            )
        )
    ]
