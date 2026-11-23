"""Job-description history: every version of every job's description,
and the request that replaces the one in force. See
models/job_description_version.py for why versions exist at all."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import RequisitionStatus


class JobDescriptionSection(BaseModel):
    """A part of the job description the three fixed fields have no place
    for -- duties, salary, benefits, working hours, place of assignment,
    documents to submit. The document's own heading and what sat under
    it, one item per line.

    The same idea as ResumeAdditionalSection on the applicant's side.
    Not read by the AI match: the score reads the description,
    qualifications and requirements only, so these sections can be
    edited without moving anyone's score."""

    title: str
    content: str


class JobDescriptionVersionRead(BaseModel):
    """One row of the history table under Create Job Opening."""

    id: int
    requisition_id: int
    job_title: str
    department: str
    requisition_status: RequisitionStatus
    version: int
    is_current: bool
    original_filename: str | None
    # False when the text was typed by hand, or when the version predates
    # the PDF being kept -- there is nothing to download either way.
    has_file: bool
    file_size: int | None
    uploaded_by_name: str | None
    created_at: datetime
    replaced_at: datetime | None
    change_note: str | None
    # Applicants whose stored match score was computed against this
    # version. Scores stored before versions existed count as version 1,
    # which is the only version there was.
    scored_count: int


class JobDescriptionVersionDetail(JobDescriptionVersionRead):
    """A version with the text it put in force -- what an applicant scored
    against it was actually measured against."""

    description: str | None
    qualifications: str | None
    requirements: str | None
    additional_sections: list[JobDescriptionSection] = Field(default_factory=list)


class JobDescriptionReplaceRequest(BaseModel):
    description: str | None = None
    qualifications: str | None = None
    requirements: str | None = None
    # None keeps the sections in force. An empty list clears them.
    additional_sections: list[JobDescriptionSection] | None = Field(default=None, max_length=30)
    # the PDF the new text was read from, if it came from one (the id
    # extract-jd returned); None when HR edited the text by hand
    jd_upload_id: str | None = None
    jd_filename: str | None = Field(default=None, max_length=255)
    change_note: str | None = Field(default=None, max_length=500)
    # HR types the job's title to confirm. Checked on the server as well
    # as in the dialog: the check exists to stop a replacement nobody
    # meant, and a check only the browser performs stops nothing.
    confirm_title: str


class JobDescriptionEditRequest(BaseModel):
    """An in-place edit from the job opening's own page. No typed-title
    confirmation and no document: it is only allowed while nobody is
    active in the pipeline, so there is no one it could move the ground
    under -- the stage-order lock's rule, applied to the text."""

    description: str | None = None
    qualifications: str | None = None
    requirements: str | None = None
    # None keeps the sections in force -- a page loaded before sections
    # existed must not wipe them by saving a description edit.
    additional_sections: list[JobDescriptionSection] | None = Field(default=None, max_length=30)
    change_note: str | None = Field(default=None, max_length=500)
