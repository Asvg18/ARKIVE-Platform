from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, EmailStr, Field, model_validator

from app.domain.password_rules import is_common_password
from app.infra.security import password_within_bcrypt_limit


def _reject_if_too_common(value: str) -> str:
    if is_common_password(value):
        raise ValueError(
            "That password is one of the most commonly used ones. "
            "Please choose something less guessable."
        )
    return value


def _reject_if_past_bcrypt_limit(value: str) -> str:
    if not password_within_bcrypt_limit(value):
        # Phrased in characters because that is what the person typing
        # can count; the true limit is 72 *bytes*, so a password made of
        # accented or non-Latin characters can be refused a little before
        # 72 of them. Rare enough to be worth the plainer sentence.
        raise ValueError("Password is too long. Please use 72 characters or fewer.")
    return value


# The one password rule for every path that *sets* a password: at least
# 8 characters, at most bcrypt's 72 bytes (infra.security), and not a
# common password (domain.password_rules). Not on LoginRequest: a wrong
# password is always 401, never 422.
Password = Annotated[
    str,
    Field(min_length=8),
    AfterValidator(_reject_if_past_bcrypt_limit),
    AfterValidator(_reject_if_too_common),
]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SignupRequest(BaseModel):
    """Applicant self-registration -- the only account-creation path
    where the person signs up unprompted. HR/evaluator accounts are
    always provisioned by an HR admin via an invite, with the invitee
    setting their own password when they accept it."""

    email: EmailStr
    password: Password
    full_name: str = Field(min_length=1, max_length=255)


class ChangePasswordRequest(BaseModel):
    """A signed-in person changing their own password. The current
    password is required even though the caller is already
    authenticated: a token proves the session, not the person holding
    it, and an unattended laptop is the exact case this asks about."""

    current_password: str
    new_password: Password

    @model_validator(mode="after")
    def _new_password_must_differ(self) -> "ChangePasswordRequest":
        if self.current_password == self.new_password:
            raise ValueError("Your new password must be different from your current one.")
        return self


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    new_password: Password


class ResetTokenStatus(BaseModel):
    """Whether a reset link is still usable, checked before the form is
    shown. Carries no email or name, so the link never reveals whose
    account it is."""

    status: Literal["valid", "expired", "used", "unknown"]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SignupResponse(BaseModel):
    message: str
