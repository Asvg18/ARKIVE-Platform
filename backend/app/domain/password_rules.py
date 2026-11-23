"""Whether a password is one of the handful everybody picks."""

from __future__ import annotations

# A short refusal list, not a complexity policy (which mostly produces
# `Password1!`): keyboard runs, "password" and its usual disguises, and
# the recurring breach-list entries. Not exhaustive; rate limiting is
# what stops online guessing. The seeded demo password is deliberately
# absent: seeded accounts never pass through this rule.
#
# Lowercase, and compared lowercase: "Password123" is no harder to guess
# than "password123".
_COMMON_PASSWORDS = frozenset(
    {
        # keyboard runs and number sequences
        "12345678",
        "123456789",
        "1234567890",
        "123123123",
        "11111111",
        "00000000",
        "87654321",
        "qwertyui",
        "qwerty123",
        "qwertyuiop",
        "asdfghjkl",
        "1q2w3e4r",
        "1qaz2wsx",
        "zaq12wsx",
        # the word itself, and its usual disguises
        "password",
        "password1",
        "password12",
        "password123",
        "passw0rd",
        "p@ssword",
        "p@ssw0rd",
        "passwords",
        "mypassword",
        "newpassword",
        "changeme",
        "letmein1",
        "letmein123",
        # perennials from public breach datasets
        "iloveyou",
        "princess",
        "sunshine",
        "football",
        "baseball",
        "superman",
        "trustno1",
        "starwars",
        "welcome1",
        "welcome123",
        "abc12345",
        "monkey123",
        "dragon123",
        "master123",
        "shadow123",
        "michael1",
        "jennifer",
        "computer",
        "whatever",
        "freedom1",
    }
)


def is_common_password(candidate: str) -> bool:
    return candidate.strip().lower() in _COMMON_PASSWORDS
