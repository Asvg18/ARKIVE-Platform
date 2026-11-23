from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.infra.config import settings


# bcrypt raises on more than 72 bytes, so every password is capped here.
# Bytes, not characters: "ñ" is two bytes.
MAX_PASSWORD_BYTES = 72


def password_within_bcrypt_limit(plain_password: str) -> bool:
    return len(plain_password.encode("utf-8")) <= MAX_PASSWORD_BYTES


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # no stored password can be over-long (schemas.auth.Password), so this
    # is just a wrong password: login answers 401 whatever was typed
    if not password_within_bcrypt_limit(plain_password):
        return False
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def create_access_token(*, user_id: int, role: str, auth_time: datetime | None = None) -> str:
    """`auth_time` is when the person actually signed in, as opposed to
    when this particular token was minted.

    Carried forward through every renewal, it gives the session a
    lifetime of its own, and is what a password change is measured
    against.

    Left unset it means now: this token starts a new session. Renewals
    pass the value they were given.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "role": role,
        "auth_time": int((auth_time or now).timestamp()),
        # role rides along for the frontend's convenience (nav without an
        # extra round trip) but isn't trusted for authorization -- see
        # infra/deps.py. only user_id is a trusted identity claim.
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def to_token_resolution(moment: datetime) -> datetime:
    """Rounds a timestamp down to whole seconds, the resolution JWT
    time claims actually have (RFC 7519 NumericDate is an integer).

    Anything compared with a token's timestamps (`password_changed_at`)
    must use this, or a token minted in the same second reads as older.
    """
    return moment.replace(microsecond=0)


def session_started_at(payload: dict) -> datetime | None:
    """When the session behind this token began.

    Falls back to `iat` for a token without auth_time. None when it has
    neither, which callers treat as untrusted."""
    for claim in ("auth_time", "iat"):
        value = payload.get(claim)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
    return None


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError (expired, bad signature, malformed) on failure."""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
