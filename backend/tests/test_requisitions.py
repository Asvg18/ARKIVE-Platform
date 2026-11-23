"""Black-box tests for HR requisition management -- creation (draft and
published), retrieval, JD extraction, and pre-screening-question
authoring. No prior coverage existed for any of this."""

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select

from app.infra.config import settings
from app.models.application_resume import ApplicationResume
from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus
from app.models.exam_slot import ExamSlot
from app.models.requisition_evaluator import RequisitionEvaluator
from app.models.stage_history import StageHistory
from app.models.stage_instance import StageInstance
from app.schemas.pipeline import JDExtractionCandidate, JDExtractionResult
from tests.conftest import auth_headers

_SAMPLE_PDF = next((Path(__file__).parent.parent / "uploads" / "resumes").glob("*.pdf"))


def test_create_requisition_as_draft(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        "/hr/requisitions",
        json={
            "title": "Draft Role",
            "department": "Testing",
            "workflow_preset": "standard",
            "publish": False,
        },
        headers=headers,
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "draft"


def test_create_requisition_published_requires_deadline(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        "/hr/requisitions",
        json={
            "title": "Published Role Missing Deadline",
            "department": "Testing",
            "workflow_preset": "standard",
            "publish": True,
        },
        headers=headers,
    )

    assert resp.status_code == 422


def test_create_requisition_published_success(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.post(
        "/hr/requisitions",
        json={
            "title": "Published Role",
            "department": "Testing",
            "workflow_preset": "standard",
            "publish": True,
            "application_deadline": "2027-01-01",
            "pre_screening_questions": [{"id": "q1", "text": "Why this role?", "required": True}],
        },
        headers=headers,
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "open"
    assert resp.json()["active_candidate_count"] == 0


def test_get_requisition(client, hr_admin, make_job):
    job = make_job(["document_upload", "final_decision"], title="Fetchable Role")
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.get(f"/hr/requisitions/{job.id}", headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "Fetchable Role"


def test_get_requisition_404(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.get("/hr/requisitions/999999999", headers=headers)

    assert resp.status_code == 404


@patch("app.services.jd_extraction.ChatOpenAI.with_structured_output")
def test_extract_jd_returns_parsed_fields(mock_llm, client, hr_admin, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    # JDExtractionCandidate, not JDExtractionResult: the model is now
    # asked to say what the document *is* alongside the four fields, and
    # the service reads that verdict before returning anything.
    mock_llm.return_value.invoke.return_value = JDExtractionCandidate(
        department="Testing",
        description="Verifies software quality across the platform.",
        qualifications="BS in Computer Science\n2+ years of QA experience",
        requirements="Manual and automated testing",
        is_job_description=True,
        document_kind="job description",
        reason="",
    )
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    with open(_SAMPLE_PDF, "rb") as f:
        resp = client.post(
            "/hr/requisitions/extract-jd",
            headers=headers,
            data={"job_title": "QA Engineer"},
            files={"jd_file": ("jd.pdf", f, "application/pdf")},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["department"] == "Testing"
    assert resp.json()["qualifications"] == "BS in Computer Science\n2+ years of QA experience"


@patch("app.services.jd_extraction.ChatOpenAI.with_structured_output")
def test_extract_jd_refuses_a_document_that_is_not_a_job_description(
    mock_llm, client, hr_admin, monkeypatch
):
    """Raised from real testing: a Professional English lecture handout was
    accepted as a job description. The stakes are higher than a wrong form
    — the fields saved here are the exact text every applicant's AI match
    score is computed against, so a wrong document silently corrupts every
    score on that job."""
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_llm.return_value.invoke.return_value = JDExtractionCandidate(
        department="",
        description="A lesson introducing workplace communication for students.",
        qualifications="",
        requirements="",
        is_job_description=False,
        document_kind="a lecture handout on professional English",
        reason="It teaches students about workplace writing rather than defining a role.",
    )
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    with open(_SAMPLE_PDF, "rb") as f:
        resp = client.post(
            "/hr/requisitions/extract-jd",
            headers=headers,
            data={"job_title": "QA Engineer"},
            files={"jd_file": ("lesson.pdf", f, "application/pdf")},
        )

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "not_a_job_description"
    # The refusal names what the file appeared to be, so it explains
    # itself rather than just saying no.
    assert "lecture handout" in detail["message"]
    assert detail["document_kind"] == "a lecture handout on professional English"


@patch("app.services.jd_extraction.ChatOpenAI.with_structured_output")
def test_extract_jd_refuses_a_document_that_yields_no_role_details(
    mock_llm, client, hr_admin, monkeypatch
):
    """The second, independent signal. The model's own classification can
    be talked into a false positive by a document that is merely *about*
    work; this one cannot, because it asks only whether anything a
    requisition needs actually came out."""
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_llm.return_value.invoke.return_value = JDExtractionCandidate(
        department="",
        description="Workplace communication.",
        qualifications="",
        requirements="",
        # Claims to be a JD; nothing usable came out of it.
        is_job_description=True,
        document_kind="job description",
        reason="",
    )
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    with open(_SAMPLE_PDF, "rb") as f:
        resp = client.post(
            "/hr/requisitions/extract-jd",
            headers=headers,
            data={"job_title": "QA Engineer"},
            files={"jd_file": ("thin.pdf", f, "application/pdf")},
        )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "not_a_job_description"


@patch("app.services.jd_extraction.ChatOpenAI.with_structured_output")
def test_extract_jd_accepts_a_terse_posting_with_criteria_but_no_overview(
    mock_llm, client, hr_admin, monkeypatch
):
    """The gate must not be so eager that it refuses real postings. A short
    listing that names its qualifications without an overview paragraph is
    a job description, and thin prose is only damning when nothing else
    came out either."""
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_llm.return_value.invoke.return_value = JDExtractionCandidate(
        department="Library Services",
        description="",
        qualifications="Bachelor's degree in Library Science",
        requirements="Cataloguing",
        is_job_description=True,
        document_kind="job description",
        reason="",
    )
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    with open(_SAMPLE_PDF, "rb") as f:
        resp = client.post(
            "/hr/requisitions/extract-jd",
            headers=headers,
            data={"job_title": "Library Assistant"},
            files={"jd_file": ("terse.pdf", f, "application/pdf")},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["qualifications"] == "Bachelor's degree in Library Science"
    # The verdict is server-side only — it must not leak into the payload
    # as a flag a client could choose to ignore.
    assert "is_job_description" not in resp.json()


def test_update_pre_screening_questions(client, hr_admin, make_job):
    job = make_job(["document_upload", "final_decision"])
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch(
        f"/hr/requisitions/{job.id}/pre-screening-questions",
        json={"questions": [{"id": "q1", "text": "Why this role?", "required": True}]},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["pre_screening_questions"] == [{"id": "q1", "text": "Why this role?", "required": True}]

    # A second write replaces the set entirely rather than appending.
    resp = client.patch(
        f"/hr/requisitions/{job.id}/pre-screening-questions",
        json={"questions": []},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["pre_screening_questions"] == []


# --- Closing, reopening and publishing a job opening (roadmap W6) ------
# `RequisitionStatus.closed` existed in the enum and in the Postgres type
# from the first migration and nothing ever assigned it. These cover the
# transition that finally does, plus the listing that keeps a closed or
# drafted posting reachable afterwards.


def _future(days: int = 30) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def test_closing_a_job_hides_it_from_applicants(client, hr_admin, make_job):
    job = make_job(["document_upload", "final_decision"], title="Soon Closed")
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    assert client.get(f"/public/jobs/{job.id}").status_code == 200

    resp = client.patch(f"/hr/requisitions/{job.id}/status", json={"status": "closed"}, headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "closed"
    # Gone from both the public board and the public detail view, which is
    # the whole point — and still fetchable by HR.
    assert client.get(f"/public/jobs/{job.id}").status_code == 404
    listed = client.get("/public/jobs").json()["items"]
    assert all(item["id"] != job.id for item in listed)
    assert client.get(f"/hr/requisitions/{job.id}", headers=headers).status_code == 200


def test_closing_is_allowed_while_candidates_are_active(
    client, hr_admin, make_job, make_application, db_session
):
    """Deliberately unlike the workflow editor's lock. Closing stops new
    applications; it does not touch the pipelines already running, and a
    position being filled is the usual reason to close one."""
    job = make_job(["document_upload", "final_decision"], title="Filled Role")
    application = make_application(job)
    db_session.flush()
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch(f"/hr/requisitions/{job.id}/status", json={"status": "closed"}, headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["active_candidate_count"] == 1
    # The in-flight candidate is untouched and still worked from HR's list.
    listed = client.get("/hr/applications", headers=headers).json()
    assert any(item["id"] == application.id for item in listed)


def test_a_closed_job_can_be_reposted_with_a_new_deadline(client, hr_admin, make_job):
    job = make_job(["document_upload", "final_decision"], title="Reposted Role")
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    client.patch(f"/hr/requisitions/{job.id}/status", json={"status": "closed"}, headers=headers)

    resp = client.patch(
        f"/hr/requisitions/{job.id}/status",
        json={"status": "open", "application_deadline": _future()},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "open"
    assert resp.json()["application_deadline"] == _future()
    assert client.get(f"/public/jobs/{job.id}").status_code == 200


def test_reopening_with_a_deadline_already_past_is_refused(client, hr_admin, make_job, db_session):
    """The trap this guard exists for: the job would be `open` and still
    absent from /public/jobs, which filters on status *and* deadline."""
    job = make_job(["document_upload", "final_decision"], title="Stale Deadline")
    job.application_deadline = date.today() - timedelta(days=1)
    db_session.flush()
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    client.patch(f"/hr/requisitions/{job.id}/status", json={"status": "closed"}, headers=headers)

    resp = client.patch(f"/hr/requisitions/{job.id}/status", json={"status": "open"}, headers=headers)

    assert resp.status_code == 409
    assert "has already passed" in resp.json()["detail"]


def test_publishing_a_draft_without_a_deadline_is_refused(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    draft = client.post(
        "/hr/requisitions",
        json={
            "title": "Unpublishable Draft",
            "department": "Testing",
            "workflow_preset": "standard",
            "publish": False,
            "pre_screening_questions": [{"id": "q1", "text": "Why this role?", "required": True}],
        },
        headers=headers,
    ).json()

    resp = client.patch(f"/hr/requisitions/{draft['id']}/status", json={"status": "open"}, headers=headers)

    assert resp.status_code == 409
    assert "application deadline" in resp.json()["detail"]

    # ...and succeeds once one is supplied, which is the route a draft had
    # no way of taking before this endpoint existed.
    resp = client.patch(
        f"/hr/requisitions/{draft['id']}/status",
        json={"status": "open", "application_deadline": _future()},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "open"


def test_a_job_cannot_be_sent_back_to_draft(client, hr_admin, make_job):
    """A draft is invisible to HR as well as to applicants, so this would
    file a live posting where nobody could find it. Closing is the
    reversible way down."""
    job = make_job(["document_upload", "final_decision"])
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch(f"/hr/requisitions/{job.id}/status", json={"status": "draft"}, headers=headers)

    assert resp.status_code == 422


def test_update_status_404(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.patch("/hr/requisitions/999999999/status", json={"status": "closed"}, headers=headers)

    assert resp.status_code == 404


def test_list_requisitions_includes_drafts_and_closed_ones(client, hr_admin, make_job):
    """The dashboard summary is open-only by design, which is what left a
    draft unreachable. This list is where the other two states live."""
    open_job = make_job(["document_upload", "final_decision"], title="Still Open")
    closed_job = make_job(["document_upload", "final_decision"], title="Now Closed")
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    draft = client.post(
        "/hr/requisitions",
        json={"title": "A Draft", "department": "Testing", "workflow_preset": "standard", "publish": False},
        headers=headers,
    ).json()
    client.patch(f"/hr/requisitions/{closed_job.id}/status", json={"status": "closed"}, headers=headers)

    resp = client.get("/hr/requisitions", headers=headers)

    assert resp.status_code == 200, resp.text
    by_id = {row["id"]: row for row in resp.json()}
    assert by_id[open_job.id]["status"] == "open"
    assert by_id[closed_job.id]["status"] == "closed"
    assert by_id[draft["id"]]["status"] == "draft"

    summary = client.get("/hr/dashboard/summary", headers=headers).json()
    summary_ids = {row["id"] for row in summary["requisitions"]}
    assert closed_job.id not in summary_ids and draft["id"] not in summary_ids


def test_a_job_nobody_applied_to_can_be_deleted(client, hr_admin, make_job):
    job = make_job(["document_upload", "final_decision"], title="Posted By Mistake")
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.delete(f"/hr/requisitions/{job.id}", headers=headers)

    assert resp.status_code == 204, resp.text
    assert client.get(f"/hr/requisitions/{job.id}", headers=headers).status_code == 404
    listed = client.get("/hr/requisitions", headers=headers).json()
    assert all(item["id"] != job.id for item in listed)


def test_deleting_a_job_takes_its_slots_and_evaluator_pool_with_it(
    client, hr_admin, evaluator, make_job, db_session
):
    """Both tables carry their own foreign key to the requisition, so
    leaving either behind would fail the delete outright -- and orphan
    the rows if it somehow didn't."""
    job = make_job(["document_upload", "examination", "final_decision"], title="Provisioned Role")
    db_session.add(ExamSlot(
        requisition_id=job.id,
        stage_type="examination",
        date="2027-03-01",
        time="09:00",
        location="Room 1",
        capacity=10,
    ))
    db_session.add(RequisitionEvaluator(requisition_id=job.id, evaluator_id=evaluator.id))
    db_session.flush()
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.delete(f"/hr/requisitions/{job.id}", headers=headers)

    assert resp.status_code == 204, resp.text
    assert db_session.scalars(
        select(ExamSlot).where(ExamSlot.requisition_id == job.id)
    ).all() == []
    assert db_session.scalars(
        select(RequisitionEvaluator).where(RequisitionEvaluator.requisition_id == job.id)
    ).all() == []


def test_an_active_candidate_blocks_the_delete(
    client, hr_admin, make_job, make_application, db_session
):
    job = make_job(["document_upload", "final_decision"], title="Has A Candidate")
    make_application(job)
    db_session.flush()
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    resp = client.delete(f"/hr/requisitions/{job.id}", headers=headers)

    assert resp.status_code == 409, resp.text
    assert "Close it instead" in resp.json()["detail"]
    assert client.get(f"/hr/requisitions/{job.id}", headers=headers).status_code == 200


def test_a_flagged_candidate_blocks_the_delete(
    client, hr_admin, make_job, make_application, db_session
):
    """A flagged candidate is frozen at skill matching waiting on HR's
    own reject-or-continue call -- as in-flight as an active one, even
    though active_candidate_count doesn't count them. Deleting the job
    would be deleting work HR still owes an answer on."""
    job = make_job(["document_upload", "skill_matching", "final_decision"], title="Flagged Only")
    application = make_application(job)
    application.status = ApplicationStatus.flagged
    db_session.flush()
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    row = next(
        item
        for item in client.get("/hr/requisitions", headers=headers).json()
        if item["id"] == job.id
    )
    assert row["active_candidate_count"] == 0
    assert row["in_flight_candidate_count"] == 1

    assert client.delete(f"/hr/requisitions/{job.id}", headers=headers).status_code == 409


def test_a_finished_application_does_not_block_the_delete_and_goes_with_it(
    client, hr_admin, make_job, make_application, make_resume, db_session
):
    """The rule HR asked for: once nobody is working through the job it
    can go, and the records of everyone who already finished go with it.
    They are counted in application_count so the confirmation can say so
    before HR agrees."""
    job = make_job(["document_upload", "skill_matching", "final_decision"], title="Round Finished")
    rejected = make_application(job)
    rejected.status = ApplicationStatus.rejected
    hired = make_application(job)
    hired.status = ApplicationStatus.hired
    make_resume(rejected)
    db_session.flush()
    rejected_id, hired_id = rejected.id, hired.id
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    row = next(
        item
        for item in client.get("/hr/requisitions", headers=headers).json()
        if item["id"] == job.id
    )
    assert row["in_flight_candidate_count"] == 0
    assert row["application_count"] == 2

    resp = client.delete(f"/hr/requisitions/{job.id}", headers=headers)

    assert resp.status_code == 204, resp.text
    remaining = db_session.scalars(
        select(CandidateApplication).where(CandidateApplication.requisition_id == job.id)
    ).all()
    assert remaining == []
    # and nothing hanging off those applications survives them
    for application_id in (rejected_id, hired_id):
        assert db_session.scalars(
            select(StageInstance).where(StageInstance.application_id == application_id)
        ).all() == []
        assert db_session.scalars(
            select(StageHistory).where(StageHistory.application_id == application_id)
        ).all() == []
    assert db_session.scalars(
        select(ApplicationResume).where(ApplicationResume.application_id == rejected_id)
    ).all() == []


def test_deleting_a_job_that_does_not_exist_is_a_404(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")

    assert client.delete("/hr/requisitions/99999", headers=headers).status_code == 404


def test_only_hr_can_delete_a_job(client, hr_admin, applicant, make_job):
    job = make_job(["document_upload", "final_decision"], title="Not Yours To Delete")
    headers = auth_headers(client, "applicant-test@arkivetesting.com")

    assert client.delete(f"/hr/requisitions/{job.id}", headers=headers).status_code == 403


# Same title in the same department can't be live twice (panel revision
# list, 15 Oct 2026). Draft and open count; closed doesn't.
def _create(client, headers, title, department, publish=False):
    return client.post(
        "/hr/requisitions",
        json={
            "title": title,
            "department": department,
            "workflow_preset": "standard",
            "publish": publish,
            "application_deadline": _future() if publish else None,
        },
        headers=headers,
    )


def test_a_duplicate_title_in_the_same_department_is_refused(client, hr_admin, make_job):
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    make_job(["document_upload", "final_decision"], title="Duplicate Check Role", department="Dup Testing")

    resp = _create(client, headers, "  duplicate check role ", "dup testing")

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "duplicate_job"


def test_the_same_title_in_another_department_is_allowed(client, hr_admin, make_job):
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    make_job(["document_upload", "final_decision"], title="Duplicate Check Role", department="Dup Testing")

    resp = _create(client, headers, "Duplicate Check Role", "Another Dup Department")

    assert resp.status_code == 201, resp.text


def _check(client, headers, **params):
    resp = client.get("/hr/requisitions/duplicate-check", params=params, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_the_builder_hears_of_a_duplicate_while_typing_the_department(client, hr_admin, make_job):
    """Said on the Review Details step, as the department is typed, rather
    than only when the finished job is published -- with the same message
    the create route refuses it with."""
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    make_job(["document_upload", "final_decision"], title="Duplicate Check Role", department="Dup Testing")

    found = _check(client, headers, title=" duplicate check role", department="DUP TESTING ")
    refused = _create(client, headers, "Duplicate Check Role", "Dup Testing")

    assert found["duplicate"] is True
    assert found["message"] == refused.json()["detail"]["message"]
    assert _check(client, headers, title="Duplicate Check Role", department="Dup Test") == {
        "duplicate": False,
        "message": None,
    }
    # nothing to compare yet while either is blank
    assert _check(client, headers, title="Duplicate Check Role", department="  ")["duplicate"] is False


def test_the_duplicate_check_ignores_a_closed_posting(client, hr_admin, make_job):
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    old = make_job(["document_upload", "final_decision"], title="Duplicate Check Role", department="Dup Testing")
    client.patch(f"/hr/requisitions/{old.id}/status", json={"status": "closed"}, headers=headers)

    assert _check(client, headers, title="Duplicate Check Role", department="Dup Testing")["duplicate"] is False


def test_a_closed_posting_does_not_block_the_same_title(client, hr_admin, make_job):
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    old = make_job(["document_upload", "final_decision"], title="Duplicate Check Role", department="Dup Testing")
    client.patch(f"/hr/requisitions/{old.id}/status", json={"status": "closed"}, headers=headers)

    resp = _create(client, headers, "Duplicate Check Role", "Dup Testing")

    assert resp.status_code == 201, resp.text


def test_reopening_is_refused_while_a_duplicate_is_live(client, hr_admin, make_job):
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    old = make_job(["document_upload", "final_decision"], title="Duplicate Check Role", department="Dup Testing")
    client.patch(f"/hr/requisitions/{old.id}/status", json={"status": "closed"}, headers=headers)
    assert _create(client, headers, "Duplicate Check Role", "Dup Testing").status_code == 201

    resp = client.patch(
        f"/hr/requisitions/{old.id}/status",
        json={"status": "open", "application_deadline": _future()},
        headers=headers,
    )

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "duplicate_job"


# Closing a job tells everyone still in its pipeline (panel revision list,
# 15 Oct 2026): an in-app notice and an email, saying their application
# continues. Applications already closed are left alone.
def test_closing_a_job_tells_applicants_still_in_its_pipeline(
    client, db_session, hr_admin, make_job, make_user
):
    from app.models.enums import UserRole
    from app.models.notification import Notification
    from app.services.applications import create_application_with_stage_instances

    headers = auth_headers(client, "hr-test@arkivetesting.com")
    job = make_job(["document_upload", "final_decision"], title="Closing Notice Role")
    people = {}
    for key, status in (("active", ApplicationStatus.active), ("flagged", ApplicationStatus.flagged),
                        ("rejected", ApplicationStatus.rejected)):
        user = make_user(f"close-{key}@arkivetesting.com", UserRole.applicant)
        application = create_application_with_stage_instances(db_session, applicant_id=user.id, requisition=job)
        application.status = status
        people[key] = user
    db_session.flush()

    with patch("app.api.hr.requisitions.send_email_safely") as send:
        resp = client.patch(f"/hr/requisitions/{job.id}/status", json={"status": "closed"}, headers=headers)
        assert resp.status_code == 200, resp.text
        # closing an already-closed job sends nothing more
        client.patch(f"/hr/requisitions/{job.id}/status", json={"status": "closed"}, headers=headers)

    emailed = sorted(call.kwargs["to"] for call in send.call_args_list)
    assert emailed == ["close-active@arkivetesting.com", "close-flagged@arkivetesting.com"]
    assert "Closing Notice Role is now closed." == send.call_args_list[0].kwargs["subject"]
    assert (
        "The Closing Notice Role opening at MSEUF has closed and is no longer accepting "
        "applications as of the moment."
    ) in send.call_args_list[0].kwargs["body"]
    # they are still in the process, so they are told it carries on
    assert "Your application is not affected." in send.call_args_list[0].kwargs["body"]

    def notices(user):
        return db_session.scalars(select(Notification).where(Notification.user_id == user.id)).all()

    assert len(notices(people["active"])) == 1
    assert len(notices(people["flagged"])) == 1
    assert notices(people["rejected"]) == []
    assert notices(people["active"])[0].message == "Closing Notice Role is now closed. Your application is not affected."


# A job is published only when it is complete (panel revision list,
# 15 Oct 2026): a deadline, a workflow that passes the rules, and
# pre-screening questions when the workflow has Pre-Screening. A draft
# may be saved without them.
def test_publishing_without_pre_screening_questions_is_refused(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    resp = client.post(
        "/hr/requisitions",
        json={
            "title": "Questionless Role",
            "department": "Publish Testing",
            "workflow_preset": "standard",
            "publish": True,
            "application_deadline": _future(),
        },
        headers=headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "publish_blocked"
    assert any("pre-screening question" in b for b in resp.json()["detail"]["blockers"])


def test_a_draft_may_be_incomplete_but_cannot_be_published_until_complete(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    draft = client.post(
        "/hr/requisitions",
        json={"title": "Half-done Role", "department": "Publish Testing", "workflow_preset": "standard", "publish": False},
        headers=headers,
    )
    assert draft.status_code == 201, draft.text
    job_id = draft.json()["id"]

    refused = client.patch(
        f"/hr/requisitions/{job_id}/status", json={"status": "open", "application_deadline": _future()}, headers=headers
    )
    assert refused.status_code == 409, refused.text

    client.patch(
        f"/hr/requisitions/{job_id}/pre-screening-questions",
        json={"questions": [{"id": "q1", "text": "Why this role?", "required": True}]},
        headers=headers,
    )
    published = client.patch(
        f"/hr/requisitions/{job_id}/status", json={"status": "open", "application_deadline": _future()}, headers=headers
    )
    assert published.status_code == 200, published.text


def test_a_job_can_be_created_with_its_own_stages_and_questions(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    stages = ["document_upload", "skill_matching", "examination_1", "shortlisting", "interview_round_1",
              "final_decision", "onboarding"]
    resp = client.post(
        "/hr/requisitions",
        json={
            "title": "Custom Stages Role",
            "department": "Publish Testing",
            "workflow_definition": stages,
            "interview_round_labels": {"interview_round_1": "Panel Interview"},
            "examination_labels": {"examination_1": "Teaching Demo"},
            "pre_screening_questions": [{"id": "q1", "text": "Why this role?", "required": True}],
            "publish": True,
            "application_deadline": _future(),
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["workflow_definition"] == stages
    assert body["interview_round_labels"]["interview_round_1"] == "Panel Interview"
    assert body["examination_labels"]["examination_1"] == "Teaching Demo"
    assert body["pre_screening_questions"][0]["text"] == "Why this role?"


def test_publishing_a_broken_workflow_is_refused(client, hr_admin):
    headers = auth_headers(client, "hr-test@arkivetesting.com")
    resp = client.post(
        "/hr/requisitions",
        json={
            "title": "Broken Stages Role",
            "department": "Publish Testing",
            "workflow_definition": ["document_upload", "interview_round_1", "final_decision"],
            "publish": True,
            "application_deadline": _future(),
        },
        headers=headers,
    )
    assert resp.status_code == 409, resp.text
    assert any("Shortlisting" in b for b in resp.json()["detail"]["blockers"])
