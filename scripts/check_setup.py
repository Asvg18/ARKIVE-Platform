"""Tells a teammate exactly why their ARKIVE setup is not working.

Written because "I copied the key exactly and the AI still doesn't work"
is unanswerable over a distance, and the repository has a genuine trap in
it: **two files named .env, both carrying an OPENAI_API_KEY line.**

  .env          (repo root)   — consumed by docker-compose, the deployment
  backend/.env                — consumed by the dev server

`app.core.config` loads `env_file=".env"`, a *relative* path, resolved
against whatever directory uvicorn was started from. Paste the key into
the root file — which visibly asks for one — and the dev server never
reads it, with nothing on screen pointing at the file. That is not a
mistake anyone should be expected to guess.

Run it from anywhere:

    python3 scripts/check_setup.py

It only reads local files and, unless you pass --skip-openai, makes one
tiny models.list() call to check the key is live. It never prints a key.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GREEN, RED, YELLOW, DIM, BOLD, OFF = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m"
)


def read_env(path: Path) -> dict[str, str]:
    """Parse a .env the way pydantic-settings does for our purposes:
    KEY=value per line, '#' comments, quotes stripped."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def describe_key(value: str) -> str:
    """Enough to identify a key without ever printing one."""
    return f"starts {value[:7]}…, {len(value)} characters"


class SetupChecker:
    """Runs the four checks and collects what's wrong along the way.

    `problems` used to be a bare module global that `bad()` reached into
    from wherever it was called. One instance per run holds it instead --
    the four `_check_*` methods are the entities that actually cause
    problems, so the list they append to belongs with them, not floating
    at module scope where anything could touch it."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.problems: list[str] = []
        self.root_values: dict[str, str] = {}
        self.backend_values: dict[str, str] = {}

    def _ok(self, msg: str) -> None:
        print(f"  {GREEN}OK{OFF}    {msg}")

    def _bad(self, msg: str, fix: str) -> None:
        print(f"  {RED}WRONG{OFF} {msg}")
        print(f"        {DIM}fix: {fix}{OFF}")
        self.problems.append(msg)

    def _warn(self, msg: str, note: str) -> None:
        print(f"  {YELLOW}NOTE{OFF}  {msg}")
        print(f"        {DIM}{note}{OFF}")

    def _check_files(self, backend_env: Path, root_env: Path) -> None:
        print(f"{BOLD}1. Settings files{OFF}")

        if backend_env.exists():
            self._ok("backend/.env exists — this is the one the dev server reads")
        else:
            self._bad(
                "backend/.env is missing",
                "cp backend/.env.example backend/.env",
            )

        if not root_env.exists():
            self._warn(
                ".env in the repo root is missing",
                "Only needed to start the database with Docker: cp .env.example .env",
            )

    def _check_key(self) -> str:
        print(f"\n{BOLD}2. OpenAI key{OFF}")

        backend_key = self.backend_values.get("OPENAI_API_KEY", "")
        root_key = self.root_values.get("OPENAI_API_KEY", "")

        if backend_key:
            self._ok(f"backend/.env has a key ({describe_key(backend_key)})")
        elif root_key:
            # The exact trap this script exists for.
            self._bad(
                "the key is in the ROOT .env, but the dev server reads backend/.env",
                "move the OPENAI_API_KEY line into backend/.env, then restart uvicorn",
            )
        else:
            self._bad(
                "no OPENAI_API_KEY found in either .env file",
                "add it to backend/.env, then restart uvicorn",
            )

        if backend_key:
            # Things that survive a copy-paste and break the key silently.
            if backend_key != backend_key.strip():
                self._bad("the key has spaces around it", "remove them")
            if backend_key.startswith(("'", '"')) or backend_key.endswith(("'", '"')):
                self._bad("the key is wrapped in quotes", "write it bare: OPENAI_API_KEY=sk-...")
            if not backend_key.startswith("sk-"):
                self._bad(
                    "the key does not start with 'sk-' — it may be truncated or the wrong value",
                    "copy it again from platform.openai.com/api-keys",
                )
            if any(ord(c) > 126 for c in backend_key):
                self._bad(
                    "the key contains a non-ASCII character — a chat app probably reformatted it",
                    "paste it from a plain-text source, not from a chat message",
                )

        return backend_key

    def _check_database(self) -> None:
        print(f"\n{BOLD}3. Database{OFF}")

        db_url = self.backend_values.get("DATABASE_URL", "")
        if not db_url:
            self._bad("backend/.env has no DATABASE_URL", "copy it from backend/.env.example")
            return

        db_port = db_url.rsplit(":", 1)[-1].split("/")[0]
        compose_port = self.root_values.get("POSTGRES_PORT", "5432")
        if db_port != compose_port:
            self._bad(
                f"port mismatch — backend/.env points at {db_port}, Docker publishes {compose_port}",
                f"make them agree (set POSTGRES_PORT={db_port} in the root .env, or change DATABASE_URL)",
            )
        else:
            self._ok(f"DATABASE_URL and Docker agree on port {db_port}")

    def _check_openai_live(self, backend_key: str, skip: bool) -> None:
        print(f"\n{BOLD}4. Is the key actually working?{OFF}")

        if skip:
            print(f"  {DIM}skipped (--skip-openai){OFF}")
            return
        if not backend_key:
            print(f"  {DIM}skipped — no key to test{OFF}")
            return

        try:
            import openai
        except ImportError:
            self._warn(
                "the openai package isn't installed in this Python",
                "run this with the same interpreter as the backend, "
                "e.g. ~/.venvs/arkive/bin/python scripts/check_setup.py",
            )
            return

        try:
            openai.OpenAI(api_key=backend_key).models.list()
            self._ok("OpenAI accepted the key")
        except openai.AuthenticationError:
            self._bad(
                "OpenAI rejected the key — it is wrong, revoked, or from another account",
                "get a fresh key from whoever owns the OpenAI account",
            )
        except openai.RateLimitError:
            self._bad(
                "the key is valid but the account is out of credit or over its quota",
                "the account owner needs to add credit — no code change will fix this",
            )
        except openai.APIConnectionError:
            self._warn(
                "couldn't reach OpenAI",
                "check your internet connection, then run this again",
            )
        except openai.OpenAIError as exc:
            self._bad(f"OpenAI returned an error: {type(exc).__name__}", str(exc)[:120])

    def run(self, skip_openai: bool) -> int:
        print(f"\n{BOLD}ARKIVE setup check{OFF}")
        print(f"{DIM}repo: {self.root}{OFF}\n")

        root_env = self.root / ".env"
        backend_env = self.root / "backend" / ".env"
        self.root_values = read_env(root_env)
        self.backend_values = read_env(backend_env)

        self._check_files(backend_env, root_env)
        backend_key = self._check_key()
        self._check_database()
        self._check_openai_live(backend_key, skip_openai)

        print()
        if self.problems:
            n = len(self.problems)
            print(f"{RED}{BOLD}{n} problem{'s' if n > 1 else ''} to fix.{OFF}")
            print(f"{DIM}Fix them, restart uvicorn, then run this again.{OFF}\n")
            return 1

        print(f"{GREEN}{BOLD}Everything checks out.{OFF}")
        print(
            f"{DIM}If the AI still fails, restart uvicorn — the key is only read at "
            f"startup.{OFF}\n"
        )
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check an ARKIVE dev setup.")
    parser.add_argument(
        "--skip-openai",
        action="store_true",
        help="don't call OpenAI; only check the files",
    )
    args = parser.parse_args()
    return SetupChecker(ROOT).run(args.skip_openai)


if __name__ == "__main__":
    sys.exit(main())
