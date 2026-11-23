"""Reading a job description PDF: what the model is asked for, and what
the API returns.
"""


from pydantic import BaseModel, Field

from app.schemas.job_description import JobDescriptionSection


class JDExtractionResult(BaseModel):
    """GPT-4o-mini structured output -- the model returns empty strings
    for anything it can't determine rather than inventing content, so HR
    always reviews/edits before publishing."""

    department: str
    description: str
    qualifications: str
    requirements: str
    # default_factory, not a default -- OpenAI's strict schema still marks
    # it required (so the model always answers it), while the class stays
    # constructible without it.
    additional_sections: list[JobDescriptionSection] = Field(default_factory=list)


class JDExtractionResponse(JDExtractionResult):
    """What POST /hr/requisitions/extract-jd returns: the fields plus an
    id for the kept PDF, passed back on create (or replace). A subclass,
    so the upload id is never part of what the model fills in."""

    jd_upload_id: str | None = None


class JDExtractionCandidate(JDExtractionResult):
    """What the model is actually asked for -- the four fields *plus*
    its reading of what the document is.

    Kept separate from JDExtractionResult (what the API returns) so the
    verdict never reaches the client as data it could ignore -- either
    the document passes and HR gets clean fields, or it's refused with
    the reason. A boolean the frontend is free to disregard isn't a gate.

    Classifying in the same call is close to free (the model's already
    read the document) and far more reliable than inferring "not a JD"
    from empty fields, since a lecture handout about workplace English
    will happily yield plausible prose for `description`."""

    is_job_description: bool
    # What it appears to be instead, in a few words ("a lecture handout on
    # professional English", "a resume", "a policy memo"). Shown to HR, so
    # the refusal explains itself rather than just saying no.
    document_kind: str
    reason: str


class JDImageReading(BaseModel):
    """GPT-4o-mini's reading of a job description PDF that is only page
    images (a scanned or photographed posting) -- see services/jd_text.py.
    The verdict comes before the transcription: `text` is only filled in
    when `is_job_description` is true, and `document_kind` / `reason`
    explain a refusal to HR the same way JDExtractionCandidate's do."""

    is_job_description: bool
    document_kind: str
    reason: str
    text: str
