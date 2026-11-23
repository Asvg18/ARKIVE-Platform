from datetime import datetime

from app.models.enums import UserRole
from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field


def avatar_url(avatar_file: str | None) -> str | None:
    """Where a profile photo is served (api/account.py), relative to the
    API's own address; null means "show initials". Every response that
    names a person carries this beside the name."""
    return f"/avatars/{avatar_file}" if avatar_file else None


class _HasAvatar(BaseModel):
    """Reads a row's avatar_file and answers with its URL instead -- the
    file name alone is an implementation detail of storage."""

    avatar_file: str | None = Field(default=None, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def avatar_url(self) -> str | None:
        return avatar_url(self.avatar_file)


class UserRead(_HasAvatar):
    """The signed-in account, as GET /auth/me reports it -- what the top
    bar shows and what Account Settings starts from."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: UserRole
    job_title: str | None = None
    department: str | None = None
    # The address a change is waiting to be confirmed at, if one is; the
    # account still signs in with `email` until then.
    pending_email: str | None = None
    # For Account Settings: "Member since" in the banner and
    # the Password card's "Last changed". Null password_changed_at means
    # never changed since the account was created.
    created_at: datetime | None = None
    password_changed_at: datetime | None = None
    # HR admins only: whether this account may manage other accounts.
    # The HR portal shows User Management only when it is true; the API
    # enforces it regardless (infra/deps.require_super_admin).
    is_super_admin: bool = False


class StaffRead(_HasAvatar):
    """hr_admin/evaluator roster for User Management — GET /hr/staff."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    role: UserRole
    job_title: str | None = None
    department: str | None = None
    created_at: datetime
    provisioning_source: str
    # Drives the roster's Active/Deactivated badge. The column has always
    # been enforced on every request; until staff could be deactivated
    # there was simply never a value worth showing.
    is_active: bool
    is_super_admin: bool = False


class WaitingInterviewRead(BaseModel):
    """An interview that would be left waiting if its evaluator's account
    were switched off -- listed in the switch-off confirmation so HR
    knows which rounds to hand to somebody else."""

    application_id: int
    candidate_name: str
    job_title: str
    stage_label: str


def _clean_optional(value: str | None) -> str | None:
    """Trims, and treats a cleared field as "not set" rather than as an
    empty string that would render as a blank line."""
    if value is None:
        return None
    value = value.strip()
    return value or None


class ProfileUpdate(BaseModel):
    """PATCH /account/profile. Omitted fields are left as they are.
    `job_title` and `department` are staff-only; the endpoint refuses
    them for an applicant."""

    full_name: str | None = Field(default=None, max_length=255)
    job_title: str | None = Field(default=None, max_length=120)
    department: str | None = Field(default=None, max_length=120)

    def cleaned(self) -> dict[str, str | None]:
        fields = self.model_dump(exclude_unset=True)
        return {key: _clean_optional(value) for key, value in fields.items()}


class EmailChangeRequest(BaseModel):
    """Asking to sign in with a different address. The password is asked
    for again for the reason ChangePasswordRequest gives: a token proves
    the session, not the person at the keyboard."""

    new_email: EmailStr
    current_password: str


class DeleteAccountRequest(BaseModel):
    """An applicant erasing their own account (services/account_erasure).
    Two proofs, both checked here as well as in the browser: the password,
    for the reason EmailChangeRequest gives, and the word DELETE typed
    out -- the last of the warnings, so nobody gets here by one click."""

    current_password: str
    confirm: str


class EmailChangeStatus(BaseModel):
    """What the confirmation page asks before showing its button. Carries
    no address, for the reason ResetTokenStatus carries none: whoever holds
    the link can read this."""

    status: str
