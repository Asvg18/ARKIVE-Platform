"""A minimal, dependency-free text-PDF writer, for seed scripts only.

Needed so a seeded candidate's PDF actually contains their résumé: HR
opens the file, the analysis falls back to its text when the structured
fields are blank, and the match score did read it until it moved to the
reviewed fields (skill_matching._resume_scoring_text). A stock PDF behind
tailored fields would contradict the record it belongs to.

Not reportlab, on purpose -- this project avoids new dependencies, and
the alternative is about sixty lines of well-specified PDF syntax. Type1
Helvetica is one of the 14 standard fonts every reader has built in, so
nothing needs embedding.

Not for user-facing documents -- no wrapping beyond what the caller
supplies, no styling, no metadata.
"""

from __future__ import annotations

_PAGE_WIDTH, _PAGE_HEIGHT = 612, 792  # US Letter, in points
_MARGIN = 54
_FONT_SIZE = 10
_LEADING = 13.5
_LINES_PER_PAGE = int((_PAGE_HEIGHT - 2 * _MARGIN) / _LEADING)


def _escape(text: str) -> str:
    """Backslash, then parens — order matters, or the escapes introduced
    for the parens would themselves get escaped."""
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _content_stream(lines: list[str]) -> bytes:
    body = [f"BT /F1 {_FONT_SIZE} Tf {_MARGIN} {_PAGE_HEIGHT - _MARGIN} Td {_LEADING} TL"]
    for line in lines:
        # A PDF text string can't contain a raw newline, and non-latin-1
        # characters can't be written in a standard-font string at all —
        # both are stripped rather than risking a malformed stream.
        safe = _escape(line).encode("latin-1", "replace").decode("latin-1")
        body.append(f"({safe}) Tj T*")
    body.append("ET")
    return "\n".join(body).encode("latin-1")


def text_pdf(lines: list[str]) -> bytes:
    """Render `lines` as a paginated, text-only PDF and return its bytes."""
    pages = [lines[i : i + _LINES_PER_PAGE] for i in range(0, len(lines), _LINES_PER_PAGE)] or [[]]

    # Object numbering: 1 = catalog, 2 = pages tree, 3 = font, then each
    # page contributes a page object and a content stream object.
    objects: dict[int, bytes] = {}
    page_ids = [4 + 2 * i for i in range(len(pages))]

    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("latin-1")
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    for page_index, page_lines in enumerate(pages):
        page_id = page_ids[page_index]
        stream_id = page_id + 1
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_WIDTH} {_PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {stream_id} 0 R >>"
        ).encode("latin-1")
        stream = _content_stream(page_lines)
        objects[stream_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for obj_id in sorted(objects):
        offsets[obj_id] = len(out)
        out += f"{obj_id} 0 obj\n".encode("latin-1") + objects[obj_id] + b"\nendobj\n"

    # The xref table must list every object number from 0 upward with no
    # gaps, so it is built over the full contiguous range rather than
    # over `objects` alone.
    xref_offset = len(out)
    highest = max(objects)
    out += f"xref\n0 {highest + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for obj_id in range(1, highest + 1):
        out += f"{offsets[obj_id]:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {highest + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("latin-1")
    return bytes(out)
