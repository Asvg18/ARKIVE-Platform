"""Shared test fixtures.

Each test runs inside a real DB transaction rolled back at teardown
(SAVEPOINT pattern), so tests hit the actual Postgres instance -- same
enums, constraints, and DFA-relevant behavior a demo would see -- without
leaving rows behind or needing a separate test database.
"""

from datetime import datetime, timezone
from typing import Callable
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.infra.config import settings
from app.infra.db import get_db
from app.infra.security import hash_password
from app.main import app
from app.models.application_resume import ApplicationResume
from app.models.enums import RequisitionStatus, UserRole
from app.models.job_requisition import JobRequisition
from app.models.stage_instance import StageInstance
from app.models.user import User
from app.schemas.decision_brief import DecisionBriefResult
from app.schemas.interview_synthesis import InterviewSynthesisResult
from app.services.applications import create_application_with_stage_instances

engine = create_engine(settings.database_url)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

TEST_PASSWORD = "test-password-123"
# any test hitting POST /evaluator/interviews/{id}/evaluate now runs the
# real Interview Synthesis Agent instead of the old fake stub --
# MOCK_RUBRIC_SCORE is the fixed rubric_coverage_score every test sees
# from the autouse mock below
MOCK_RUBRIC_SCORE = 72.5
MOCK_BRIEF_VERDICT = "Mocked decision brief verdict for tests."
MOCK_BRIEF_RATIONALE = "Mocked decision brief rationale for tests."


@pytest.fixture(autouse=True)
def mock_ai_agents(monkeypatch):
    """Autouse so no test file can silently start making real OpenAI
    calls by forgetting to mock one -- moved here after test_evaluator.
    py's suite was found to have gone from ~18s to ~37s once its
    endpoint started calling a real agent. Harmless for tests that never
    reach these agents.

    Patches each service module's own ChatOpenAI symbol rather than a
    method on the shared class -- both agents import the same ChatOpenAI,
    so patching ChatOpenAI.with_structured_output would hand *both* of
    them whichever schema was configured last. That's exactly what
    happened when the Decision Brief Agent was added and started
    receiving InterviewSynthesisResult objects.
    """
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    with (
        patch("app.services.interview_synthesis.ChatOpenAI") as synthesis_llm,
        patch("app.services.decision_brief.ChatOpenAI") as brief_llm,
    ):
        synthesis_llm.return_value.with_structured_output.return_value.invoke.return_value = (
            InterviewSynthesisResult(
                rubric_coverage_score=MOCK_RUBRIC_SCORE,
                summary="Mocked interview synthesis for tests.",
            )
        )
        brief_llm.return_value.with_structured_output.return_value.invoke.return_value = (
            DecisionBriefResult(verdict=MOCK_BRIEF_VERDICT, rationale=MOCK_BRIEF_RATIONALE)
        )
        yield synthesis_llm


@pytest.fixture(autouse=True)
def pinned_feature_flags(monkeypatch):
    """Pins config that changes how many model calls a request makes, so
    the suite does not depend on whatever is in the developer's .env.

    Found the hard way: switching RAG_QUERY_EXPANSION on in backend/.env
    turned eight passing tests red, because the Context Router then made
    a QueryExpansion call their mocks knew nothing about. The tests were
    not wrong -- the suite was reading ambient configuration, so the same
    commit passed or failed depending on a gitignored file. That is a
    property worth eliminating whichever way the flag happens to be set.

    Pinned off, because off is the path the vast majority of these tests
    are written against. Tests that are *about* expansion turn it back on
    with their own monkeypatch, which runs after this and wins.
    """
    monkeypatch.setattr(settings, "rag_query_expansion", False)


@pytest.fixture(autouse=True)
def no_real_email(monkeypatch):
    """The suite never reaches a real mail server, whatever backend/.env
    says. Same lesson as pinned_feature_flags, with a worse failure: once
    SMTP was configured for real (Gmail, 20 Sep 2026), every test that
    triggered an email without stubbing it sent one -- from the team's
    own account, to made-up test addresses -- and the suite slowed to a
    crawl on network round-trips. Enough bounces can get that account
    rate-limited, which would break the emails the app actually needs.

    Blanking the settings puts the suite back on the path it was written
    for ("SMTP is not configured in tests", test_password_reset.py): every
    send is a logged no-op. Tests about email capture send_email_safely,
    or break smtplib, themselves.
    """
    monkeypatch.setattr(settings, "smtp_host", None)
    monkeypatch.setattr(settings, "smtp_username", None)
    monkeypatch.setattr(settings, "smtp_password", None)


@pytest.fixture(autouse=True)
def job_description_uploads(tmp_path, monkeypatch):
    """Job-description PDFs are kept on disk since versions were added, and
    a rolled-back transaction can't take a file back off disk -- so every
    test writes them to its own temporary folder instead of uploads/."""
    from app.services import file_storage

    folder = tmp_path / "job_descriptions"
    monkeypatch.setattr(file_storage, "_JD_UPLOAD_DIR", folder)
    return folder


@pytest.fixture(autouse=True)
def avatar_uploads(tmp_path, monkeypatch):
    """Profile photos go to a per-test folder for the same reason job
    descriptions do: a rolled-back transaction can't take a file back."""
    from app.services import file_storage

    folder = tmp_path / "avatars"
    monkeypatch.setattr(file_storage, "_AVATAR_DIR", folder)
    return folder


@pytest.fixture(autouse=True)
def no_kept_resume_readings():
    """Scanned-resume readings are kept in memory for the upload to reuse
    (services/resume_text.py). Tests share PDFs byte for byte, so without
    this one test's reading would answer the next test's model call."""
    from app.services import resume_text

    resume_text._readings.clear()
    yield
    resume_text._readings.clear()


@pytest.fixture()
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session: Session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def make_user(db_session: Session) -> Callable[..., User]:
    def _make(email: str, role: UserRole, *, super_admin: bool = False) -> User:
        user = User(
            email=email,
            hashed_password=hash_password(TEST_PASSWORD),
            full_name=email,
            role=role,
            auth_provider="local",
            provisioning_source="test",
            email_verified_at=datetime.now(timezone.utc),
            is_super_admin=super_admin,
        )
        db_session.add(user)
        db_session.flush()
        return user

    return _make


@pytest.fixture()
def hr_admin(make_user) -> User:
    """A super admin, because every installation's first HR admin is one
    (scripts/create_first_admin.py) and most tests play that person.
    Tests about what an HR admin *without* account management can do use
    plain_hr_admin."""
    return make_user("hr-test@arkivetesting.com", UserRole.hr_admin, super_admin=True)


@pytest.fixture()
def plain_hr_admin(make_user) -> User:
    """An HR admin who is not a super admin: every hiring page, no User
    Management."""
    return make_user("hr-plain-test@arkivetesting.com", UserRole.hr_admin)


@pytest.fixture()
def applicant(make_user) -> User:
    return make_user("applicant-test@arkivetesting.com", UserRole.applicant)


@pytest.fixture()
def evaluator(make_user) -> User:
    return make_user("evaluator-test@arkivetesting.com", UserRole.evaluator)


@pytest.fixture()
def make_job(db_session: Session, hr_admin: User) -> Callable[..., JobRequisition]:
    def _make(
        workflow_definition: list[str],
        title: str = "Test Job",
        department: str = "Testing",
        description: str | None = None,
        qualifications: str | None = None,
        requirements: str | None = None,
    ) -> JobRequisition:
        job = JobRequisition(
            title=title,
            department=department,
            description=description,
            qualifications=qualifications,
            requirements=requirements,
            status=RequisitionStatus.open,
            workflow_definition=workflow_definition,
            created_by=hr_admin.id,
        )
        db_session.add(job)
        db_session.flush()
        return job

    return _make


@pytest.fixture()
def make_application(db_session: Session, applicant: User):
    def _make(job: JobRequisition):
        return create_application_with_stage_instances(
            db_session, applicant_id=applicant.id, requisition=job
        )

    return _make


@pytest.fixture()
def make_resume(db_session: Session) -> Callable[..., ApplicationResume]:
    def _make(
        application,
        *,
        experience: list[dict] | None = None,
        education: list[dict] | None = None,
        skills: list[str] | None = None,
        certifications: list[str] | None = None,
        raw_extracted_text: str = "",
    ) -> ApplicationResume:
        resume = ApplicationResume(
            application_id=application.id,
            original_filename="resume.pdf",
            stored_path="/tmp/resume.pdf",
            experience=experience or [],
            education=education or [],
            skills=skills or [],
            certifications=certifications or [],
            raw_extracted_text=raw_extracted_text,
        )
        db_session.add(resume)
        db_session.flush()
        return resume

    return _make


def auth_headers(client: TestClient, email: str, password: str = TEST_PASSWORD) -> dict[str, str]:
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def give_confirmed_time(db_session: Session, stage_instance_id: int) -> None:
    """Books a time the applicant has confirmed onto an interview round.
    The evaluator's form stays locked until one exists (panel revision
    list, 15 Oct 2026, step 19c), so a test about the scorecard itself
    sets one up first rather than walking the whole scheduling flow."""
    instance = db_session.get(StageInstance, stage_instance_id)
    instance.payload = {
        **(instance.payload or {}),
        "schedule": {
            "date": "2030-01-15",
            "time": "09:00",
            "mode": "in_person",
            "location": "Room 1",
            "meeting_link": None,
        },
        "schedule_confirmation": {
            "response": "confirmed",
            "asked_at": None,
            "responded_at": None,
            "note": None,
        },
    }
    db_session.flush()
