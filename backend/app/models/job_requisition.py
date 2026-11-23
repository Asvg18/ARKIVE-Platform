from datetime import date

from sqlalchemy import JSON, Date, Enum, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base
from app.models.enums import RequisitionStatus
from app.models.mixins import TimestampMixin


class JobRequisition(Base, TimestampMixin):
    __tablename__ = "job_requisitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    department: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    # extracted from an uploaded JD PDF via GPT-4o-mini rather than typed
    # by HR. nullable since every requisition created before this flow
    # existed never had one.
    qualifications: Mapped[str | None] = mapped_column(Text, default=None)
    requirements: Mapped[str | None] = mapped_column(Text, default=None)
    # everything else the job description says that the three fields
    # above have no place for (salary, benefits, documents to submit...),
    # as [{title, content}] -- see schemas.job_description.
    # JobDescriptionSection. Not part of what the AI match reads.
    additional_sections: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    # the current version's source file name -- the full history, with
    # the files themselves, is JobDescriptionVersion
    jd_filename: Mapped[str | None] = mapped_column(String(255), default=None)
    # cached OpenAI embedding of this JD's text -- computed lazily on
    # first use and reused thereafter. Cleared whenever HR replaces the
    # job description (services/job_descriptions.replace_job_description),
    # so the next applicant is embedded against the new text; scores
    # already stored are untouched and name the version they used.
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True, default=None)
    # shown to applicants as "Applications close in N days." nullable --
    # required to publish (enforced in RequisitionCreateRequest), but
    # drafts and pre-existing requisitions can have none.
    application_deadline: Mapped[date | None] = mapped_column(Date, default=None)
    status: Mapped[RequisitionStatus] = mapped_column(
        Enum(RequisitionStatus, name="requisition_status"),
        default=RequisitionStatus.draft,
    )

    # ordered list of StageType strings, e.g. ["document_upload",
    # "skill_matching", ...]. JSON, not a join table -- the DFA generator
    # reads it whole, it's never queried by individual stage.
    workflow_definition: Mapped[list[str]] = mapped_column(JSON)

    # per-job display label for each generic interview_round_k slot in
    # use, e.g. {"interview_round_1": "Technical Screen"}. purely
    # additive -- workflow_definition stays a plain list[str]. see
    # stage_labels.resolve_stage_label().
    interview_round_labels: Mapped[dict[str, str] | None] = mapped_column(
        JSON, nullable=True, default=None
    )

    # same idea as interview_round_labels, but for the generic
    # examination_1..4 slots. separate column rather than merged in,
    # since these are conceptually distinct slot families with
    # independent key spaces.
    examination_labels: Mapped[dict[str, str] | None] = mapped_column(
        JSON, nullable=True, default=None
    )

    # how long each interview round runs, in minutes, e.g.
    # {"interview_round_1": 45} -- cuts the evaluator's free ranges into
    # fixed slots. A round missing
    # here uses domain.interview_slots.default_duration.
    interview_durations: Mapped[dict[str, int] | None] = mapped_column(
        JSON, nullable=True, default=None
    )

    # HR-authored AI Pre-Screening questions, list[dict] matching
    # schemas.pipeline.PreScreeningQuestion ({id, text, required}). exam-
    # availability steps are NOT stored here -- those get auto-derived
    # from workflow_definition's examination_k stages at request time.
    pre_screening_questions: Mapped[list[dict] | None] = mapped_column(
        JSON, nullable=True, default=None
    )

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
