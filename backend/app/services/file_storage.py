"""Local-disk storage for uploaded files: resumes, documents, job
description PDFs and profile photos. The interface would not change for
S3-compatible storage."""

import re
import uuid
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_RESUME_UPLOAD_DIR = _BACKEND_ROOT / "uploads" / "resumes"
_DOCUMENT_UPLOAD_DIR = _BACKEND_ROOT / "uploads" / "documents"


def save_resume_file(pdf_bytes: bytes) -> str:
    """Writes pdf_bytes under a fresh UUID filename, never the
    browser-reported original name -- no collision risk, and nothing
    here ever builds a path from user input."""
    _RESUME_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}.pdf"
    (_RESUME_UPLOAD_DIR / stored_name).write_bytes(pdf_bytes)
    return f"uploads/resumes/{stored_name}"


def resolve_resume_path(stored_path: str) -> Path:
    return _BACKEND_ROOT / stored_path


def save_supplemental_document_file(pdf_bytes: bytes) -> str:
    """Same UUID-filename convention as save_resume_file, just kept in its
    own directory since these back a different entity (ApplicationDocument,
    not ApplicationResume)."""
    _DOCUMENT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}.pdf"
    (_DOCUMENT_UPLOAD_DIR / stored_name).write_bytes(pdf_bytes)
    return f"uploads/documents/{stored_name}"


def resolve_document_path(stored_path: str) -> Path:
    return _BACKEND_ROOT / stored_path


# Job-description PDFs, kept (not just read for extraction) so a job's
# history can produce the document it came from. The upload id handed back
# to the browser is the file's own random name -- the only thing a later
# request can point at, and nothing a path can be built from.
_JD_UPLOAD_DIR = _BACKEND_ROOT / "uploads" / "job_descriptions"
_JD_UPLOAD_ID = re.compile(r"[0-9a-f]{32}")


def save_job_description_file(pdf_bytes: bytes) -> str:
    """Writes the PDF under a fresh UUID and returns that UUID as the
    upload id."""
    _JD_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    upload_id = uuid.uuid4().hex
    (_JD_UPLOAD_DIR / f"{upload_id}.pdf").write_bytes(pdf_bytes)
    return upload_id


def job_description_stored_path(upload_id: str) -> str | None:
    """The stored_path for an upload id, or None if the id is malformed or
    no such file was saved. Validated by shape first, so a crafted id can
    never reach the filesystem as anything but a 32-character hex name."""
    if not _JD_UPLOAD_ID.fullmatch(upload_id or ""):
        return None
    if not (_JD_UPLOAD_DIR / f"{upload_id}.pdf").is_file():
        return None
    return f"uploads/job_descriptions/{upload_id}.pdf"


def resolve_job_description_path(stored_path: str) -> Path:
    # By file name within the one directory, so the stored value can't
    # walk anywhere else even if a row were edited by hand.
    return _JD_UPLOAD_DIR / Path(stored_path).name


# Profile photos are served without sign-in (an <img> cannot send the
# bearer token), so the random file name is the key, only ever given out
# by the signed-in API. A replaced photo gets a new name, so caches never
# show the old one.
_AVATAR_DIR = _BACKEND_ROOT / "uploads" / "avatars"
_AVATAR_NAME = re.compile(r"[0-9a-f]{32}\.(jpg|png|webp)")

MAX_AVATAR_BYTES = 2 * 1024 * 1024

AVATAR_MEDIA_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def sniff_avatar_format(data: bytes) -> str | None:
    """The image format from the file's own first bytes, never from its
    name or the browser's claimed type -- both are whatever the uploader
    says. Only the three formats every browser draws; SVG is deliberately
    absent, since it can carry script."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def save_avatar_file(data: bytes, image_format: str) -> str:
    """Writes the photo under a fresh random name and returns that name."""
    _AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{image_format}"
    (_AVATAR_DIR / name).write_bytes(data)
    return name


def resolve_avatar_path(name: str) -> Path | None:
    """The file for a photo name, or None. Validated by shape first, so a
    crafted name can never reach the filesystem as a path."""
    if not _AVATAR_NAME.fullmatch(name or ""):
        return None
    path = _AVATAR_DIR / name
    return path if path.is_file() else None


def delete_avatar_file(name: str | None) -> None:
    """Removes a replaced or cleared photo. Quietly does nothing for a
    name that is malformed or already gone."""
    path = resolve_avatar_path(name) if name else None
    if path is not None:
        path.unlink(missing_ok=True)
