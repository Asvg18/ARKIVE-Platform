from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.infra.db import get_db
from app.infra.security import (
    create_access_token,
    decode_access_token,
    session_started_at,
)
from app.models.enums import UserRole
from app.models.user import User

bearer_scheme = HTTPBearer()

# carries a fresh token once the current one is past halfway; the client
# swaps it in silently, so an active session slides instead of ending at
# 60 minutes (one header instead of a refresh-token pair)
RENEWED_TOKEN_HEADER = "X-Renewed-Token"

# How long a session may last however continuously it is used, so a
# stolen, renewed token is never a permanent key. Covers a working day.
ABSOLUTE_SESSION_LIFETIME = timedelta(hours=12)


def get_current_user(
    response: Response,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        raise unauthorized

    user_id = payload.get("user_id")
    if user_id is None:
        raise unauthorized

    # loads the current row instead of trusting the token's role claim --
    # this is what makes a role change or deactivation take effect
    # immediately instead of waiting for the old token to expire
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized

    if not _session_still_valid(payload, user):
        raise unauthorized

    _renew_if_past_halfway(response, payload, user)
    return user


def _session_still_valid(payload: dict, user: User) -> bool:
    """The two reasons a valid, unexpired token is refused anyway: its
    *session* (which outlives any one token) is too old, or began before
    the password changed. A token with no session start is not trusted.
    """
    started = session_started_at(payload)
    if started is None:
        return False

    # 1. The session has simply run long enough. Renewal means a token's
    #    own expiry never arrives while someone keeps working, so without
    #    this a session lasts forever -- and so does a stolen token that
    #    keeps being used.
    if datetime.now(timezone.utc) - started > ABSOLUTE_SESSION_LIFETIME:
        return False

    # 2. The password changed after this session began. That is what
    #    makes a reset remove whoever else is signed in. The person who
    #    performed the change keeps working, because those endpoints hand
    #    back a token whose session starts after the change.
    if user.password_changed_at is not None and started < user.password_changed_at:
        return False

    return True


def _renew_if_past_halfway(response: Response, payload: dict, user: User) -> None:
    """Issues a replacement token once the current one is more than half
    spent (at most one per half-lifetime of use). Silent on failure: a
    malformed exp/iat just means no renewal."""
    exp, iat = payload.get("exp"), payload.get("iat")
    if not isinstance(exp, (int, float)) or not isinstance(iat, (int, float)):
        return
    lifetime = exp - iat
    if lifetime <= 0:
        return
    now = datetime.now(timezone.utc).timestamp()
    if (now - iat) < lifetime / 2:
        return
    # Carries the original sign-in forward rather than restarting it --
    # without this the renewal *is* the endless session, since each new
    # token would look freshly authenticated.
    response.headers[RENEWED_TOKEN_HEADER] = create_access_token(
        user_id=user.id, role=user.role.value, auth_time=session_started_at(payload)
    )


def require_role(*allowed_roles: UserRole):
    """Dependency factory: gates a route to a set of roles. This is the
    real authorization boundary — checked against the fresh DB row from
    get_current_user, never the JWT's embedded role claim."""

    def _check(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource",
            )
        return current_user

    return _check


def require_super_admin(
    current_user: Annotated[User, Depends(require_role(UserRole.hr_admin))],
) -> User:
    """Gates account management -- inviting staff, switching accounts off
    and on, granting super admin -- to HR admins who are super admins.
    Read off the live row like every role check, so removing someone's
    super admin takes effect on their very next request."""
    if not current_user.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a super admin can manage accounts.",
        )
    return current_user
