"""The job-description upload refuses documents that are not job
descriptions.

Without it any PDF is accepted (testing found a lecture handout from a
Professional English subject getting through). Not cosmetic -- the stored
description/qualifications/requirements are the exact text every
applicant's match score gets computed against, so a bad document
silently corrupts every score attached to that job.

Two independent signals, because the service uses two: the model's own
reading of what the document *is*, and a structural check on whether
anything usable came out. The first can be talked into a false positive
by a document merely *about* hiring; the second can't, since it only
asks whether a role's details are present.

Imports domain.jd_rules rather than the extraction service -- the rules
are pure, so this file costs nothing to run, while the service drags in
langchain_openai, whose import alone can take minutes on a cold
filesystem."""

import pytest

from app.schemas.pipeline import JDExtractionCandidate
from app.domain.jd_rules import NotAJobDescriptionError, yields_nothing_usable


def _candidate(**overrides) -> JDExtractionCandidate:
    base = dict(
        department="Computing",
        description=(
            "The IT Systems Administrator maintains the university's servers, "
            "networks and identity systems, and supports faculty and staff."
        ),
        qualifications="Bachelor's degree in IT or related field\nThree years of experience",
        requirements="Linux server administration\nNetwork configuration",
        is_job_description=True,
        document_kind="job description",
        reason="",
    )
    base.update(overrides)
    return JDExtractionCandidate(**base)


# --- The structural check ---------------------------------------------


def test_a_real_job_description_yields_something_usable():
    assert yields_nothing_usable(_candidate()) is False


def test_a_document_with_no_role_detailsyields_nothing_usable():
    """The lecture-handout shape: some prose may come back, but nothing
    that defines a role."""
    assert yields_nothing_usable(
        _candidate(description="Workplace communication.", qualifications="", requirements="")
    ) is True


def test_criteria_alone_are_enough_to_be_usable():
    """A terse posting that lists what it wants without an overview
    paragraph is still a job description. The check must not refuse it —
    thin prose is only damning when nothing else came out either."""
    assert yields_nothing_usable(
        _candidate(description="", qualifications="Bachelor's degree in Library Science", requirements="")
    ) is False


def test_a_long_description_alone_is_enough_to_be_usable():
    assert yields_nothing_usable(
        _candidate(qualifications="", requirements="")
    ) is False


# --- The refusal itself -----------------------------------------------


def test_the_error_carries_what_the_document_appeared_to_be():
    """The message HR sees names the document, so the refusal explains
    itself instead of just saying no."""
    exc = NotAJobDescriptionError("a lecture handout on professional English", "It teaches workplace writing.")
    assert exc.document_kind == "a lecture handout on professional English"
    assert exc.reason == "It teaches workplace writing."


def test_the_error_falls_back_to_a_readable_kind():
    """The model is asked for `document_kind`, but a blank one must not
    produce 'That file looks like , not a job description.'"""
    exc = NotAJobDescriptionError("", "")
    assert exc.document_kind == "not a job description"


@pytest.mark.parametrize(
    "kind",
    ["a resume", "a university policy memo", "a course syllabus", "a set of meeting minutes"],
)
def test_every_refusal_names_its_document(kind):
    assert NotAJobDescriptionError(kind, "").document_kind == kind
