"""An applicant deleting their own account (27 Sep 2026).

The decision under test: erase the person, keep the record. Everything
that identifies them goes -- name, email, photo, password, resumes,
documents, letter of intent, their inbox -- and their open applications
are withdrawn, but HR keeps each application's history, under
"Deleted applicant".
"""

from pathlib import Path

from sqlalchemy import select

from app.models.application_document import ApplicationDocument
from app.models.application_resume import ApplicationResume
from app.models.enums import ApplicationStatus, StageType, UserRole
from app.models.notification import Notification
from app.models.stage_instance import StageInstance
from app.models.user import User
from app.services.account_erasure import DELETED_NAME
from app.services.notifications import notify
from tests.conftest import TEST_PASSWORD, auth_headers

WORKFLOW = ["document_upload", "skill_matching", "final_decision"]


def _delete(client, headers, *, password=TEST_PASSWORD, confirm="DELETE"):
    return client.post(
        "/account/delete", json={"current_password": password, "confirm": confirm}, headers=headers
    )


def _uploaded(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(b"%PDF-1.4 stand-in")
    return path


def test_deleting_erases_the_person_and_withdraws_what_is_open(
    client, db_session, applicant, make_job, make_application, tmp_path
):
    application = make_application(make_job(WORKFLOW))
    resume_file = _uploaded(tmp_path, "resume.pdf")
    document_file = _uploaded(tmp_path, "reference.pdf")
    db_session.add(
        ApplicationResume(
            application_id=application.id,
            original_filename="Ada_Resume.pdf",
            stored_path=str(resume_file),  # absolute, so it resolves to itself
            full_name="Ada Applicant",
            email="ada@example.com",
            phone="0917 000 0000",
        )
    )
    db_session.add(
        ApplicationDocument(
            application_id=application.id,
            label="Reference letter",
            original_filename="reference.pdf",
            stored_path=str(document_file),
        )
    )
    upload_stage = db_session.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.document_upload,
        )
    )
    upload_stage.payload = {"letter_of_intent": "Dear HR, I am Ada...", "submitted": True}
    db_session.add(Notification(user_id=applicant.id, title="Exam booked", message="Your exam is scheduled."))
    db_session.flush()

    headers = auth_headers(client, applicant.email)
    old_email = applicant.email

    resp = _delete(client, headers)
    assert resp.status_code == 204, resp.text

    db_session.expire_all()
    user = db_session.get(User, applicant.id)
    assert user.full_name == DELETED_NAME
    assert user.email != old_email and user.email.endswith(".invalid")
    assert user.is_active is False
    assert user.avatar_file is None

    assert db_session.get(type(application), application.id).status == ApplicationStatus.withdrawn
    assert db_session.scalars(
        select(ApplicationResume).where(ApplicationResume.application_id == application.id)
    ).all() == []
    assert db_session.scalars(
        select(ApplicationDocument).where(ApplicationDocument.application_id == application.id)
    ).all() == []
    assert not resume_file.exists() and not document_file.exists()

    payload = db_session.get(StageInstance, upload_stage.id).payload
    assert "letter_of_intent" not in payload
    assert payload["submitted"] is True, "the record of the stage itself stays"

    assert db_session.scalars(select(Notification).where(Notification.user_id == applicant.id)).all() == []


def test_staff_notices_about_them_keep_what_happened_but_not_the_name(
    client, db_session, applicant, hr_admin, evaluator, make_user, make_job, make_application
):
    """HR's and evaluators' notices stay, as part of the hiring record,
    but the name written into them goes with the rest of the person
    (Aerron, 17 Oct 2026). Found by who acted or which application the
    notice is about; anyone else named in it is left alone."""
    applicant.full_name = "Liza Ramos"
    other = make_user("bea-test@arkivetesting.com", UserRole.applicant)
    other.full_name = "Bea Cruz"
    application = make_application(make_job(WORKFLOW, title="Registrar Officer"))
    # She did it.
    declined = notify(
        db_session, user_id=hr_admin.id, actor_id=applicant.id, application_id=application.id,
        title="Offer declined", message="Liza Ramos declined the offer for Registrar Officer.",
    )
    # Someone else did it, about her application.
    assigned = notify(
        db_session, user_id=evaluator.id, actor_id=hr_admin.id, application_id=application.id,
        title="New interview assigned",
        message="You've been assigned to conduct Final Interview for Liza Ramos (Registrar Officer).",
    )
    reschedule = notify(
        db_session, user_id=hr_admin.id, actor_id=evaluator.id, application_id=application.id,
        title="Reschedule request",
        message=(
            f"{evaluator.full_name} requested to reschedule Liza Ramos's "
            "Final Interview to 20 Oct at 9:00 AM."
        ),
    )
    # Not about her.
    unrelated = notify(
        db_session, user_id=hr_admin.id, actor_id=other.id, application_id=None,
        title="Offer declined", message="Bea Cruz declined the offer for Registrar Officer.",
    )
    db_session.flush()

    assert _delete(client, auth_headers(client, applicant.email)).status_code == 204

    db_session.expire_all()
    assert db_session.get(Notification, declined.id).message == (
        "Deleted applicant declined the offer for Registrar Officer."
    )
    assert db_session.get(Notification, assigned.id).message == (
        "You've been assigned to conduct Final Interview for Deleted applicant (Registrar Officer)."
    )
    assert db_session.get(Notification, reschedule.id).message == (
        f"{evaluator.full_name} requested to reschedule Deleted applicant's "
        "Final Interview to 20 Oct at 9:00 AM."
    )
    assert db_session.get(Notification, unrelated.id).message == (
        "Bea Cruz declined the offer for Registrar Officer."
    )
    assert db_session.get(Notification, declined.id).title == "Offer declined"
    assert not any("Liza Ramos" in message for message in db_session.scalars(select(Notification.message)))


def test_only_the_whole_name_is_swapped(client, db_session, applicant, evaluator, make_job, make_application):
    """A short name inside a longer word is not the name."""
    applicant.full_name = "Ana"
    application = make_application(make_job(WORKFLOW, title="Data Analyst"))
    picked = notify(
        db_session, user_id=evaluator.id, actor_id=applicant.id, application_id=application.id,
        title="Interview time picked",
        message="Ana picked 2026-10-20 at 09:00 for their Final Interview (Data Analyst).",
    )
    db_session.flush()

    assert _delete(client, auth_headers(client, applicant.email)).status_code == 204

    db_session.expire_all()
    assert db_session.get(Notification, picked.id).message == (
        "Deleted applicant picked 2026-10-20 at 09:00 for their Final Interview (Data Analyst)."
    )


def test_the_session_ends_and_the_old_sign_in_no_longer_works(client, applicant):
    email = applicant.email  # the row's own email is the placeholder afterwards
    headers = auth_headers(client, email)
    assert _delete(client, headers).status_code == 204

    assert client.get("/auth/me", headers=headers).status_code == 401
    login = client.post("/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert login.status_code == 401


def test_the_email_is_free_to_sign_up_again(client, applicant):
    email = applicant.email
    assert _delete(client, auth_headers(client, email)).status_code == 204

    fresh = client.post(
        "/auth/signup", json={"email": email, "password": "a-new-start-123", "full_name": "Starting Over"}
    )
    assert fresh.status_code == 201, fresh.text


def test_a_decided_application_keeps_its_outcome(
    client, db_session, applicant, make_job, make_application
):
    """Only what is still open is withdrawn; a hire or a rejection is a
    decision HR already made and is left as it was."""
    hired = make_application(make_job(WORKFLOW, title="Hired Job"))
    hired.status = ApplicationStatus.hired
    rejected = make_application(make_job(WORKFLOW, title="Rejected Job"))
    rejected.status = ApplicationStatus.rejected
    flagged = make_application(make_job(WORKFLOW, title="Flagged Job"))
    flagged.status = ApplicationStatus.flagged
    db_session.flush()

    assert _delete(client, auth_headers(client, applicant.email)).status_code == 204

    db_session.expire_all()
    assert db_session.get(type(hired), hired.id).status == ApplicationStatus.hired
    assert db_session.get(type(rejected), rejected.id).status == ApplicationStatus.rejected
    assert db_session.get(type(flagged), flagged.id).status == ApplicationStatus.withdrawn


def test_a_wrong_password_or_a_missing_confirmation_changes_nothing(client, db_session, applicant):
    headers = auth_headers(client, applicant.email)

    assert _delete(client, headers, password="not-my-password").status_code == 403
    assert _delete(client, headers, confirm="delete me").status_code == 422

    db_session.expire_all()
    user = db_session.get(User, applicant.id)
    assert user.is_active is True
    assert user.full_name != DELETED_NAME


def test_staff_cannot_delete_their_own_account(client, db_session, evaluator, hr_admin):
    for person in (evaluator, hr_admin):
        resp = _delete(client, auth_headers(client, person.email))
        assert resp.status_code == 403, resp.text

    db_session.expire_all()
    assert db_session.get(User, evaluator.id).is_active is True
    assert db_session.get(User, hr_admin.id).is_active is True
