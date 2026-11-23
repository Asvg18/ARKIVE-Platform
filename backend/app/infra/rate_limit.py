"""Volume limits for login and signup, kept in memory: ARKIVE runs as one
instance, and several would need a shared store instead.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

# Five failures inside fifteen minutes, then a fifteen-minute cool-off.
# Generous enough that a person mistyping a password a few times is never
# affected, tight enough that an online guessing attack is not viable.
MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60

# far above real use per address; a hiring fair behind one campus NAT
# could reach it, so raise it then rather than remove the limit
SIGNUP_MAX_ACCOUNTS = 10
SIGNUP_WINDOW_SECONDS = 60 * 60


@dataclass
class _Bucket:
    failures: list[float] = field(default_factory=list)


# process-local -- swap for Redis/Postgres if ARKIVE ever runs more than
# one backend process, or a per-process counter lets an attacker get
# MAX_ATTEMPTS tries per worker
_ATTEMPTS: dict[str, _Bucket] = {}
_LOCK = threading.Lock()


def _prune(bucket: _Bucket, now: float, window_seconds: int) -> None:
    bucket.failures = [t for t in bucket.failures if now - t < window_seconds]


def seconds_until_retry(
    key: str,
    max_attempts: int = MAX_ATTEMPTS,
    window_seconds: int = WINDOW_SECONDS,
) -> int:
    """0 when the caller may proceed, otherwise how long they must wait.
    For login this is checked *before* the password is verified, so a
    locked-out caller cannot keep the CPU busy hashing."""
    now = time.monotonic()
    with _LOCK:
        bucket = _ATTEMPTS.get(key)
        if bucket is None:
            return 0
        _prune(bucket, now, window_seconds)
        if len(bucket.failures) < max_attempts:
            return 0
        # Unblocks once the oldest attempt ages out of the window.
        return max(1, int(window_seconds - (now - bucket.failures[0])))


def record_attempt(key: str, window_seconds: int = WINDOW_SECONDS) -> None:
    """Counts one attempt against `key`. Login records only failures, keyed
    per email *and* per client address (address alone lets one attacker
    cycle accounts; email alone lets anyone lock a user out). Signup
    records every account it creates, and only time clears those."""
    now = time.monotonic()
    with _LOCK:
        bucket = _ATTEMPTS.setdefault(key, _Bucket())
        _prune(bucket, now, window_seconds)
        bucket.failures.append(now)


def clear(key: str) -> None:
    """Called on a successful login, so a few fat-fingered attempts
    followed by the right password leave nothing behind. Deliberately
    *not* called on a successful signup — there, success is the thing
    being counted."""
    with _LOCK:
        _ATTEMPTS.pop(key, None)


def reset_all() -> None:
    """Test-only: keeps one test's lockout from leaking into the next."""
    with _LOCK:
        _ATTEMPTS.clear()
