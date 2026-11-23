from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.job_description import JobDescriptionSection


class JobListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    department: str
    description: str | None
    qualifications: str | None
    requirements: str | None
    # the rest of the posting (salary, benefits, documents to submit...)
    additional_sections: list[JobDescriptionSection] = []
    application_deadline: date | None
    stage_count: int
    created_at: datetime


class JobListResponse(BaseModel):
    """Paged job-board results.

    `total` is the count matching current filters *before* limit/offset,
    so the UI can say "Showing 6 of 13" without fetching everything.
    `departments` is deliberately NOT filtered by the active query --
    the full set across all open jobs, so filter controls stay stable
    instead of disappearing as the user narrows results.
    """

    items: list[JobListItem]
    total: int
    departments: list[str]


class JobDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    department: str
    description: str | None
    qualifications: str | None
    requirements: str | None
    # the rest of the posting (salary, benefits, documents to submit...)
    additional_sections: list[JobDescriptionSection] = []
    application_deadline: date | None
    workflow_definition: list[str]
    # the same stages in this job's own words (a custom interview round
    # name, say) -- what the applicant's job browser lists as "the hiring
    # process for this role", so it reads the way the application will
    stage_labels: list[str] = []
    created_at: datetime
