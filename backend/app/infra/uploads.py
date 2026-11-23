"""The rules every PDF upload has to satisfy."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile, status

# resumes/JDs/reference letters are text with the occasional logo -- a
# year of real use fits under 5 MB, and a scanned multi-page PDF (the
# largest legitimate case here) still lands well inside 10 MB
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _too_large() -> HTTPException:
    megabytes = MAX_UPLOAD_BYTES // (1024 * 1024)
    return HTTPException(
        status.HTTP_413_CONTENT_TOO_LARGE,
        # Says the limit, so the person can tell whether their file is
        # slightly over or in the wrong format entirely.
        detail=f"This file is too large. The maximum is {megabytes} MB.",
    )


def reject_if_not_pdf(upload: UploadFile) -> None:
    if upload.content_type != "application/pdf" and not (upload.filename or "").lower().endswith(".pdf"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Only PDF files are supported."
        )


async def read_within_limit(upload: UploadFile) -> bytes:
    """The bytes of the upload, or a 413 if there are too many of them.
    UploadFile.size (only declared by the multipart parser) refuses early;
    the bytes actually read are the real check. uploads/ has no quota and
    shares the database's disk."""
    declared = upload.size
    if declared is not None and declared > MAX_UPLOAD_BYTES:
        raise _too_large()

    data = await upload.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise _too_large()
    return data
