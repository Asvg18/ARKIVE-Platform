"""Whether an uploaded document is actually a job description. Pure: no
imports from the rest of the app (see ExtractedJobFields).
"""

from __future__ import annotations

from typing import Protocol

__all__ = ["ExtractedJobFields", "NotAJobDescriptionError", "yields_nothing_usable"]


class ExtractedJobFields(Protocol):
    """The three fields this rule reads off whatever the extractor
    returned. A `Protocol`, so app.schemas.pipeline.JDExtractionCandidate
    satisfies it without the domain importing app.schemas
    (tests/test_architecture.py)."""

    description: str
    qualifications: str
    requirements: str


class NotAJobDescriptionError(Exception):
    """The upload is a readable PDF, but not a job description.

    Unlike AIExtractionFailedError (the extraction broke), the extraction
    worked and the *document* is wrong."""

    def __init__(self, document_kind: str, reason: str):
        self.document_kind = (document_kind or "").strip() or "not a job description"
        self.reason = (reason or "").strip()
        super().__init__(self.reason or self.document_kind)


# deliberately generous -- this only bites when the criteria fields are
# *also* empty, so a terse-but-real posting never gets caught by it
_MIN_USABLE_DESCRIPTION_CHARS = 80


def yields_nothing_usable(parsed: ExtractedJobFields) -> bool:
    """True when nothing a requisition actually needs came out. The saved
    text is what every match score is computed against, so a document
    that is not a job description must be refused.

    The second of two independent signals: the model's own
    classification can be fooled by a document merely *about* work, but
    this only checks whether role details are present. True only when
    there is neither an overview nor any criteria."""
    thin_description = len(parsed.description.strip()) < _MIN_USABLE_DESCRIPTION_CHARS
    no_criteria = not parsed.qualifications.strip() and not parsed.requirements.strip()
    return thin_description and no_criteria
