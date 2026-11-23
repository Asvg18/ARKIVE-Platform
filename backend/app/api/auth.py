from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.account import account_read
from app.infra.config import settings
from app.infra.db import get_db
from app.infra import rate_limit
from app.infra.deps import RENEWED_TOKEN_HEADER, get_current_user
from app.infra.security import (
    create_access_token,
    hash_password,
    to_token_resolution,
    verify_password,
)
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    ResetTokenStatus,
    SignupRequest,
    SignupResponse,
    TokenResponse,
)
from app.schemas.user import UserRead
from app.services import password_reset
from app.services import email_verification

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password",
    )

    # keyed on email *and* client address -- address alone would let one
    # attacker work through many accounts on one connection, email alone
    # would let anyone lock a known user out by failing logins on purpose
    client_host = request.client.host if request.client else "unknown"
    attempt_key = f"{body.email.lower()}|{client_host}"

    # Checked before the password is verified, so a locked-out caller
    # cannot keep the server busy computing bcrypt hashes.
    retry_after = rate_limit.seconds_until_retry(attempt_key)
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Too many failed sign-in attempts. "
                f"Try again in {max(1, retry_after // 60)} minute(s)."
            ),
            headers={"Retry-After": str(retry_after)},
        )

    user = db.scalar(select(User).where(User.email == body.email))
    # Compare against a hash even when no user was found (bcrypt.checkpw
    # against a dummy hash) so login timing doesn't leak whether an email
    # exists in the system.
    dummy_hash = "$2b$12$CwaJ4sh1uY7A5C1u1F4CIOHNiaMdY0iJmiKMRuWG1Aq5cvOTdmSpi"
    password_ok = verify_password(body.password, user.hashed_password if user else dummy_hash)

    if user is None or not password_ok or not user.is_active:
        rate_limit.record_attempt(attempt_key)
        raise invalid_credentials
    if user.email_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "email_not_verified", "message": "Please verify your email address before signing in."},
        )

    # A few fat-fingered attempts followed by the right password should
    # leave nothing behind.
    rate_limit.clear(attempt_key)
    token = create_access_token(user_id=user.id, role=user.role.value)
    return TokenResponse(access_token=token)


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, request: Request, db: Session = Depends(get_db)) -> SignupResponse:
    """Create an applicant account and send its email verification link."""
    # keyed on client address alone -- unlike login there's no second
    # identifier, the email of an account that doesn't exist yet is
    # whatever the caller decides to type
    client_host = request.client.host if request.client else "unknown"
    signup_key = f"signup|{client_host}"

    retry_after = rate_limit.seconds_until_retry(
        signup_key,
        max_attempts=rate_limit.SIGNUP_MAX_ACCOUNTS,
        window_seconds=rate_limit.SIGNUP_WINDOW_SECONDS,
    )
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Too many accounts have been created from this network recently. "
                f"Try again in {max(1, retry_after // 60)} minute(s)."
            ),
            headers={"Retry-After": str(retry_after)},
        )

    existing = db.scalar(select(User).where(User.email == body.email))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A user with this email already exists.")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=UserRole.applicant,
        auth_provider="local",
        provisioning_source="self_registration",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    email_verification.issue_verification(db, user)

    # recorded *after* the account exists, and never cleared -- this
    # limits successful creation, not failed attempts, so a caller can't
    # reset their own budget by succeeding
    rate_limit.record_attempt(signup_key, window_seconds=rate_limit.SIGNUP_WINDOW_SECONDS)

    return SignupResponse(message="Account created. Check your email to verify your address.")


@router.get("/verify-email/{token}", response_model=ResetTokenStatus)
def verify_email_status(token: str, db: Session = Depends(get_db)) -> ResetTokenStatus:
    return ResetTokenStatus(status=email_verification.token_status(email_verification.find_token(db, token)))


@router.post("/verify-email/{token}", status_code=status.HTTP_204_NO_CONTENT)
def verify_email(token: str, db: Session = Depends(get_db)) -> Response:
    found = email_verification.find_token(db, token)
    if found is None or email_verification.token_status(found) != "valid":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This verification link is invalid or expired.")
    email_verification.spend_token(db, found)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
def resend_verification(body: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)) -> Response:
    client_host = request.client.host if request.client else "unknown"
    for key, max_attempts, window in (
        (f"verification|{client_host}", rate_limit.SIGNUP_MAX_ACCOUNTS, rate_limit.SIGNUP_WINDOW_SECONDS),
        (f"verification-email|{body.email.lower()}", rate_limit.MAX_ATTEMPTS, rate_limit.WINDOW_SECONDS),
    ):
        if rate_limit.seconds_until_retry(key, max_attempts=max_attempts, window_seconds=window):
            return Response(status_code=status.HTTP_202_ACCEPTED)
        rate_limit.record_attempt(key, window_seconds=window)
    user = db.scalar(select(User).where(User.email == body.email))
    if user is not None and user.is_active and user.email_verified_at is None:
        email_verification.issue_verification(db, user)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.get("/me", response_model=UserRead)
def me(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> UserRead:
    # Built by Account Settings' own reader, so the top bar and the
    # settings page can never describe the account differently.
    return account_read(db, current_user)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(
    body: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)
) -> Response:
    """Starts a password reset (unauthenticated: the person cannot sign
    in).

    **Always answers 202**, whether or not the email has an account, so
    the endpoint never reveals which addresses are registered.
    """
    client_host = request.client.host if request.client else "unknown"

    # two limits: mail one network can trigger, and mail one inbox can
    # receive
    for key, max_attempts, window in (
        (f"forgot|{client_host}", rate_limit.SIGNUP_MAX_ACCOUNTS, rate_limit.SIGNUP_WINDOW_SECONDS),
        (f"forgot-email|{body.email.lower()}", rate_limit.MAX_ATTEMPTS, rate_limit.WINDOW_SECONDS),
    ):
        if rate_limit.seconds_until_retry(key, max_attempts=max_attempts, window_seconds=window):
            # Deliberately still a 202. A 429 here would leak that this
            # address had been asked about recently, which is most of
            # what the generic answer exists to hide.
            return Response(status_code=status.HTTP_202_ACCEPTED)
        rate_limit.record_attempt(key, window_seconds=window)

    password_reset.issue_reset(
        db, email=body.email, reset_url_base=settings.frontend_base_url
    )
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.get("/reset-password/{token}", response_model=ResetTokenStatus)
def reset_password_status(token: str, db: Session = Depends(get_db)) -> ResetTokenStatus:
    """Lets the reset page tell someone their link is stale *before*
    they choose a new password, rather than after."""
    return ResetTokenStatus(
        status=password_reset.token_status(password_reset.find_token(db, token))
    )


@router.post("/reset-password/{token}", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    token: str, body: ResetPasswordRequest, db: Session = Depends(get_db)
) -> Response:
    """Spends the link without creating a browser session.

    A password reset is a security-sensitive change. Requiring a fresh
    sign-in makes the result explicit to the account owner and avoids
    leaving a newly authenticated session behind on a shared device.
    """
    found = password_reset.find_token(db, token)
    state = password_reset.token_status(found)
    # `found is None` is redundant with state ("unknown" covers it) but
    # says so to the type checker without an assert, which -O strips.
    if found is None or state != "valid":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "unknown": "This reset link is not valid. Request a new one.",
                "used": "This reset link has already been used. Request a new one.",
                "expired": "This reset link has expired. Request a new one.",
            }[state],
        )

    user = password_reset.spend_token(db, found, hash_password(body.new_password))
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(timezone.utc)
        db.commit()

    # Every session begun on the old password has ended: spend_token sets
    # password_changed_at, which infra/deps checks. A login lockout is not
    # cleared here (it is keyed on the client address too); it ages out.
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Lets a signed-in person (any role) change their own password.

    Rate-limited by user id, not client address: the attacker here is at
    an unlocked laptop, on the legitimate address.
    """
    attempt_key = f"change-password|{current_user.id}"

    # Checked before the password is verified, same order as login, so a
    # locked-out caller cannot keep the server busy hashing.
    retry_after = rate_limit.seconds_until_retry(attempt_key)
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Too many incorrect attempts. "
                f"Try again in {max(1, retry_after // 60)} minute(s)."
            ),
            headers={"Retry-After": str(retry_after)},
        )

    if not verify_password(body.current_password, current_user.hashed_password):
        rate_limit.record_attempt(attempt_key)
        # Deliberately not 401: the client treats any 401 as an expired
        # session and signs the user out, which would throw away the
        # form they are standing in over a typo.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The current password you entered is incorrect.",
        )

    rate_limit.clear(attempt_key)
    # Whole seconds, matching a token's own resolution -- see
    # infra.security.to_token_resolution for why that matters here.
    now = to_token_resolution(datetime.now(timezone.utc))
    current_user.hashed_password = hash_password(body.new_password)
    # Every session that began before this moment stops working (see
    # infra/deps.py). That is what makes this endpoint mean what the
    # person pressing it assumes it means.
    current_user.password_changed_at = now
    db.commit()

    # ...including the caller's own, so they get a replacement token in
    # the response header: this session continues, every other one ends.
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers[RENEWED_TOKEN_HEADER] = create_access_token(
        user_id=current_user.id, role=current_user.role.value
    )
    return response
