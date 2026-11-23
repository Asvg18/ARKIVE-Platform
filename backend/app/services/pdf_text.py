"""Shared PDF reading for JD and resume extraction: the pypdf reader, the
error types, and the page images of a PDF with no text layer (for
resume_text and jd_text)."""

import base64
import io
import logging

from pypdf import PdfReader
from pypdf.errors import PdfReadError

_log = logging.getLogger(__name__)

# long side, in pixels -- enough for 10pt type on a full page, small
# enough not to pay for a 4000px phone photo
_MAX_SIDE = 2000
# logos, icons and decorative rules are not pages of text
_MIN_SIDE = 200


class PdfTextExtractionError(Exception):
    """The uploaded file isn't a readable PDF, or has no extractable text
    (e.g. a scanned image with no text layer)."""


class ExtractionNotConfiguredError(Exception):
    """No OPENAI_API_KEY is set — see backend/.env.example."""


class AIExtractionFailedError(Exception):
    """The OpenAI call itself failed (network, rate limit, refusal, etc.)."""


def extract_pdf_text(pdf_bytes: bytes, *, max_chars: int) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except PdfReadError as exc:
        raise PdfTextExtractionError("Couldn't read this file as a PDF.") from exc

    if not text:
        raise PdfTextExtractionError(
            "Couldn't extract any text from this PDF. It may be a scanned "
            "image without a text layer. Try a text-based PDF or fill in "
            "the fields manually."
        )
    return text[:max_chars]


def pdf_page_images(pdf_bytes: bytes, *, max_pages: int, max_images: int) -> list[str]:
    """The pictures on the first `max_pages` pages, as JPEG data URLs, in
    page order.

    The embedded images, not rendered pages (no rasteriser needed; an
    image-only PDF has one image per page). An undecodable image is
    skipped."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        page_count = len(reader.pages)
    except PdfReadError:
        return []
    urls: list[str] = []
    for index in range(min(page_count, max_pages)):
        try:
            embedded = list(reader.pages[index].images)
        except Exception:
            _log.info("Couldn't list the images on page %s of an uploaded PDF", index + 1)
            continue
        for image in embedded:
            try:
                picture = image.image
                if picture is None or min(picture.size) < _MIN_SIDE:
                    continue
                picture = picture.convert("RGB")
                picture.thumbnail((_MAX_SIDE, _MAX_SIDE))
                buffer = io.BytesIO()
                picture.save(buffer, format="JPEG", quality=85)
            except Exception:
                _log.info("Skipped an undecodable image on page %s of an uploaded PDF", index + 1)
                continue
            urls.append("data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii"))
            if len(urls) >= max_images:
                return urls
    return urls
