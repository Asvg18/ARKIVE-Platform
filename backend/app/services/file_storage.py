"""Storage for uploaded files: resumes, documents, job description PDFs
and profile photos.

Two modes, picked by settings (see app.infra.config):

* Local only (the default). Files live under uploads/ on disk, as they
  always have.
* Bucket-backed, when upload_bucket and the AWS_* settings are all set.
  Every save is also written to an S3-compatible bucket (Neon Object
  Storage), which holds the permanent copy. The local folders become a
  cache: a file missing from disk is fetched from the bucket the first
  time something asks for its path. That keeps every caller exactly as
  it was, since they all work with local Paths, while letting the disk
  be wiped (a redeploy, a free-tier restart) without losing anyone's
  resume.
"""

import logging
import re
import uuid
from pathlib import Path

from app.infra.config import settings

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_RESUME_UPLOAD_DIR = _BACKEND_ROOT / "uploads" / "resumes"
_DOCUMENT_UPLOAD_DIR = _BACKEND_ROOT / "uploads" / "documents"

# Error codes S3-compatible servers use for "no such object".
_MISSING_CODES = {"404", "NoSuchKey", "NotFound"}

_client = None


def _bucket_enabled() -> bool:
    return all(
        (
            settings.upload_bucket,
            settings.aws_endpoint_url_s3,
            settings.aws_access_key_id,
            settings.aws_secret_access_key,
        )
    )


def _s3():
    """The bucket client, built on first use so local-only runs (and the
    test suite) never import boto3 at all."""
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config

        _client = boto3.client(
            "s3",
            endpoint_url=settings.aws_endpoint_url_s3,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region or "us-east-1",
            # Neon Object Storage speaks SigV4 and path-style URLs only.
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=10,
                read_timeout=30,
            ),
        )
    return _client


def _key(path: Path) -> str:
    """The bucket key for a stored file: uploads/<folder>/<file name>.
    Built from the folder's own name, so it matches the stored_path
    column for resumes and documents and needs no other bookkeeping."""
    return f"uploads/{path.parent.name}/{path.name}"


def _store(path: Path, data: bytes) -> None:
    """Writes data to path and, in bucket mode, to the bucket too. A
    failed bucket write removes the local copy and raises, so the caller
    never records a file that is not safely kept."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if not _bucket_enabled():
        return
    try:
        _s3().put_object(Bucket=settings.upload_bucket, Key=_key(path), Body=data)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _pull(path: Path) -> None:
    """In bucket mode, fetches the file into the local cache when it is
    not already on disk. A file the bucket does not have is left missing,
    which callers already treat as "no such file"."""
    if path.is_file() or not _bucket_enabled():
        return
    from botocore.exceptions import ClientError

    try:
        response = _s3().get_object(Bucket=settings.upload_bucket, Key=_key(path))
        data = response["Body"].read()
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in _MISSING_CODES:
            return
        raise
    path.parent.mkdir(parents=True, exist_ok=True)
    # Written beside the target and renamed into place, so a request that
    # arrives mid-download never serves half a file.
    partial = path.with_name(path.name + ".part")
    partial.write_bytes(data)
    partial.replace(path)


def delete_stored_file(path: Path) -> None:
    """Removes a stored file from disk and, in bucket mode, from the
    bucket. A file already gone is not an error: the goal is that it's
    gone. A bucket failure is raised as OSError, the same family a failed
    unlink raises, so callers that already handle that keep working."""
    path.unlink(missing_ok=True)
    if not _bucket_enabled():
        return
    try:
        _s3().delete_object(Bucket=settings.upload_bucket, Key=_key(path))
    except Exception as error:
        raise OSError(f"Could not remove {path.name} from the file bucket") from error


def save_resume_file(pdf_bytes: bytes) -> str:
    """Writes pdf_bytes under a fresh UUID filename, never the
    browser-reported original name -- no collision risk, and nothing
    here ever builds a path from user input."""
    stored_name = f"{uuid.uuid4().hex}.pdf"
    _store(_RESUME_UPLOAD_DIR / stored_name, pdf_bytes)
    return f"uploads/resumes/{stored_name}"


def resolve_resume_path(stored_path: str) -> Path:
    path = _BACKEND_ROOT / stored_path
    _pull(path)
    return path


def save_supplemental_document_file(pdf_bytes: bytes) -> str:
    """Same UUID-filename convention as save_resume_file, just kept in its
    own directory since these back a different entity (ApplicationDocument,
    not ApplicationResume)."""
    stored_name = f"{uuid.uuid4().hex}.pdf"
    _store(_DOCUMENT_UPLOAD_DIR / stored_name, pdf_bytes)
    return f"uploads/documents/{stored_name}"


def resolve_document_path(stored_path: str) -> Path:
    path = _BACKEND_ROOT / stored_path
    _pull(path)
    return path


# Job-description PDFs, kept (not just read for extraction) so a job's
# history can produce the document it came from. The upload id handed back
# to the browser is the file's own random name -- the only thing a later
# request can point at, and nothing a path can be built from.
_JD_UPLOAD_DIR = _BACKEND_ROOT / "uploads" / "job_descriptions"
_JD_UPLOAD_ID = re.compile(r"[0-9a-f]{32}")


def save_job_description_file(pdf_bytes: bytes) -> str:
    """Writes the PDF under a fresh UUID and returns that UUID as the
    upload id."""
    upload_id = uuid.uuid4().hex
    _store(_JD_UPLOAD_DIR / f"{upload_id}.pdf", pdf_bytes)
    return upload_id


def job_description_stored_path(upload_id: str) -> str | None:
    """The stored_path for an upload id, or None if the id is malformed or
    no such file was saved. Validated by shape first, so a crafted id can
    never reach the filesystem as anything but a 32-character hex name."""
    if not _JD_UPLOAD_ID.fullmatch(upload_id or ""):
        return None
    path = _JD_UPLOAD_DIR / f"{upload_id}.pdf"
    _pull(path)
    if not path.is_file():
        return None
    return f"uploads/job_descriptions/{upload_id}.pdf"


def resolve_job_description_path(stored_path: str) -> Path:
    # By file name within the one directory, so the stored value can't
    # walk anywhere else even if a row were edited by hand.
    path = _JD_UPLOAD_DIR / Path(stored_path).name
    _pull(path)
    return path


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
    name = f"{uuid.uuid4().hex}.{image_format}"
    _store(_AVATAR_DIR / name, data)
    return name


def resolve_avatar_path(name: str) -> Path | None:
    """The file for a photo name, or None. Validated by shape first, so a
    crafted name can never reach the filesystem as a path."""
    if not _AVATAR_NAME.fullmatch(name or ""):
        return None
    path = _AVATAR_DIR / name
    _pull(path)
    return path if path.is_file() else None


def delete_avatar_file(name: str | None) -> None:
    """Removes a replaced or cleared photo. Quietly does nothing for a
    name that is malformed or already gone."""
    if name and _AVATAR_NAME.fullmatch(name):
        delete_stored_file(_AVATAR_DIR / name)
