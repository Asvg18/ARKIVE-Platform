"""An applicant deleting their own account: *erase the person, keep the
record* (erase_applicant). Applicants only; staff are switched off by a
super admin.
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.infra.security import hash_password
from app.models.application_document import ApplicationDocument
from app.models.application_resume import ApplicationResume
from app.models.candidate_application import CandidateApplication
from app.models.email_change import EmailChangeToken
from app.models.enums import ApplicationStatus, UserRole
from app.models.notification import Notification
from app.models.password_reset import PasswordResetToken
from app.models.stage_instance import StageInstance
from app.models.user import User
from app.services.file_storage import (
    delete_stored_file,
    resolve_avatar_path,
    resolve_document_path,
    resolve_resume_path,
)

__all__ = ["DELETED_NAME", "NotAnApplicantError", "delete_files", "erase_applicant", "is_erased"]

DELETED_NAME = "Deleted applicant"
# The placeholder address an erased account is given. Reserved (.invalid)
# so it can never be delivered to, and what tells an erased account from
# one that is only switched off.
ERASED_EMAIL_DOMAIN = "deleted.arkive.invalid"

# Stage-payload keys holding something the applicant wrote about
# themselves, rather than a record of the hiring process.
_PERSONAL_PAYLOAD_KEYS = ("letter_of_intent",)

# Applications still in play. The rest (hired, rejected, withdrawn) are
# already decided and are left as they are.
_OPEN_STATUSES = (ApplicationStatus.active, ApplicationStatus.flagged)


class NotAnApplicantError(Exception):
    """Staff accounts are closed by an HR admin, not by themselves."""


def erase_applicant(db: Session, user: User) -> list[Path]:
    """Erases the person from `user` and their uploads, in the session.

    The account row stays, because applications, scores and evaluations
    point at it and are HR's history. Removed or replaced:

    - open applications (active, flagged) are withdrawn, as "Cancel
      Application" does;
    - the name becomes DELETED_NAME, the email a placeholder (freeing the
      real address for a new sign-up), photo and staff fields are
      cleared, and the password becomes one nobody knows;
    - the account is switched off, which ends every session at once
      (infra/deps.py checks is_active on each request);
    - every resume (the file and the row read from it), extra document
      and letter of intent;
    - their own notifications and pending email-change or reset links;
    - their name inside notices staff were sent about them.

    Kept: each application's stage history, scores and the evaluations
    staff wrote, now under DELETED_NAME.

    Caller owns db.commit(). Returns the files to delete, which the caller
    removes only *after* the commit succeeds.
    """
    if user.role != UserRole.applicant:
        raise NotAnApplicantError

    files: list[Path] = []
    applications = db.scalars(
        select(CandidateApplication).where(CandidateApplication.applicant_id == user.id)
    ).all()
    application_ids = [a.id for a in applications]

    for application in applications:
        if application.status in _OPEN_STATUSES:
            application.status = ApplicationStatus.withdrawn

    if application_ids:
        for resume in db.scalars(
            select(ApplicationResume).where(ApplicationResume.application_id.in_(application_ids))
        ):
            files.append(resolve_resume_path(resume.stored_path))
            db.delete(resume)

        for document in db.scalars(
            select(ApplicationDocument).where(ApplicationDocument.application_id.in_(application_ids))
        ):
            files.append(resolve_document_path(document.stored_path))
            db.delete(document)

        for instance in db.scalars(
            select(StageInstance).where(StageInstance.application_id.in_(application_ids))
        ):
            payload = instance.payload or {}
            if any(key in payload for key in _PERSONAL_PAYLOAD_KEYS):
                # A new dict, so SQLAlchemy sees the JSON column change.
                instance.payload = {k: v for k, v in payload.items() if k not in _PERSONAL_PAYLOAD_KEYS}

    db.execute(delete(Notification).where(Notification.user_id == user.id))
    _remove_name_from_staff_notices(db, user, application_ids)
    db.execute(delete(EmailChangeToken).where(EmailChangeToken.user_id == user.id))
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))

    photo = resolve_avatar_path(user.avatar_file) if user.avatar_file else None
    if photo is not None:
        files.append(photo)

    user.full_name = DELETED_NAME
    # Unique, never deliverable (.invalid is reserved for exactly this),
    # and not guessable from the real address.
    user.email = f"deleted-{user.id}-{secrets.token_hex(4)}@{ERASED_EMAIL_DOMAIN}"
    user.hashed_password = hash_password(secrets.token_urlsafe(32))
    user.avatar_file = None
    user.job_title = None
    user.department = None
    user.is_active = False

    return files


def _remove_name_from_staff_notices(db: Session, user: User, application_ids: list[int]) -> None:
    """Swaps the name for DELETED_NAME in what staff were told about this
    person ("Liza Ramos declined the offer for ..."). The notice itself
    stays: what happened and when is part of the hiring record.

    Must run before user.full_name is overwritten. Cannot reach a notice
    written under an earlier name, or one whose application was deleted
    with its job."""
    name = user.full_name.strip()
    if not name or name == DELETED_NAME:
        return
    about_them = [Notification.actor_id == user.id]
    if application_ids:
        about_them.append(Notification.application_id.in_(application_ids))
    # The whole name only, so an "Ana" leaves "Data Analyst" alone.
    whole_name = re.compile(rf"(?<!\w){re.escape(name)}(?!\w)")
    for notice in db.scalars(
        select(Notification).where(Notification.user_id != user.id, or_(*about_them))
    ):
        notice.message = whole_name.sub(DELETED_NAME, notice.message)


def is_erased(user: User) -> bool:
    """Whether this account was erased by erase_applicant -- not merely
    switched off, which a staff account can be and still be someone."""
    return user.email.endswith(f"@{ERASED_EMAIL_DOMAIN}")


def delete_files(files: list[Path]) -> None:
    """Removes what erase_applicant listed, once its changes are saved.
    A file already missing is not an error -- the goal is that it's gone."""
    for path in files:
        delete_stored_file(path)
