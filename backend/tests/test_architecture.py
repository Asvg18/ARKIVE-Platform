"""The dependency rule, as a test rather than a paragraph in a doc.

    api -> services -> domain, and anything may use infra.

app/domain/ is the pure inner ring -- hiring rules decidable from their
arguments alone (DFA, stage sufficiency gate, workflow sensibleness
rules, scorecard, scoring algorithms). This file keeps it I/O-free.

Worth a test, not just a convention, because the violation is never
deliberate -- it arrives as one convenient import (a domain rule needing
"just this one field" off a Pydantic schema, a Session passed down
"temporarily") and nothing fails, so it stays. A rule that only reads a
few fields of a schema takes a Protocol instead (as jd_rules.py does).

Parses imports rather than importing the modules, so it stays fast and
can't be fooled by a lazy import inside a function body.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"

# models.enums is the one carve-out, deliberate: the enums *are* domain
# vocabulary (StageType, ApplicationStatus), they just live under
# models/ because SQLAlchemy columns reference them, and pull in no
# engine, session, or table metadata
DOMAIN_ALLOWED_APP_IMPORTS = {"app.domain", "app.models.enums"}

# Third-party machinery that has no business inside the pure core.
FORBIDDEN_IN_DOMAIN = {"sqlalchemy", "fastapi", "langchain", "langchain_openai", "openai", "httpx"}


def _python_files(package: str) -> list[Path]:
    return sorted((APP / package).rglob("*.py"))


def _imported_modules(path: Path) -> set[str]:
    """Every module named by an import in this file, dotted-path form."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # a relative import cannot leave its own package
                continue
            if node.module:
                # `from app.domain import dfa` names app.domain.dfa, not app.domain
                found.update(f"{node.module}.{alias.name}" for alias in node.names)
                found.add(node.module)
    return found


def _covered_by(module: str, allowed: set[str]) -> bool:
    return any(module == a or module.startswith(f"{a}.") for a in allowed)


def _ids(paths: list[Path]) -> list[str]:
    return [p.relative_to(APP).as_posix() for p in paths]


domain_files = _python_files("domain")
service_files = _python_files("services")


def test_domain_package_is_not_empty() -> None:
    """Guards the guard: if app/domain/ were renamed away, every test below
    would pass vacuously by iterating over nothing."""
    assert len(domain_files) > 5


@pytest.mark.parametrize("path", domain_files, ids=_ids(domain_files))
def test_domain_imports_nothing_from_the_app_but_enums(path: Path) -> None:
    """The dependency arrow points inward. A domain rule may not reach out
    to a router, a service, a schema, or a table."""
    offenders = sorted(
        m
        for m in _imported_modules(path)
        if m.startswith("app.") and not _covered_by(m, DOMAIN_ALLOWED_APP_IMPORTS)
    )
    assert not offenders, (
        f"{path.relative_to(APP)} imports {offenders} from outside app/domain/. "
        "The pure core may only use app.domain.* and app.models.enums — take the "
        "value as a parameter or a Protocol instead."
    )


@pytest.mark.parametrize("path", domain_files, ids=_ids(domain_files))
def test_domain_has_no_io_machinery(path: Path) -> None:
    """No database, no web framework, no model client. Every rule in here is
    decidable from its arguments, which is what makes it cheap to test."""
    offenders = sorted(
        m for m in _imported_modules(path) if m.split(".")[0] in FORBIDDEN_IN_DOMAIN
    )
    assert not offenders, (
        f"{path.relative_to(APP)} imports {offenders}. app/domain/ is I/O-free by "
        "construction — that belongs in app/services/ or app/infra/."
    )


@pytest.mark.parametrize("path", service_files, ids=_ids(service_files))
def test_services_do_not_import_the_presentation_layer(path: Path) -> None:
    """Services are called by routers, never the reverse. An import going the
    other way is the first sign of business logic drifting back up into HTTP
    handlers — which is what this refactor moved out of them."""
    offenders = sorted(m for m in _imported_modules(path) if m.startswith("app.api"))
    assert not offenders, (
        f"{path.relative_to(APP)} imports {offenders}. A service must not depend on a "
        "router; move the shared code down into app/services/ or app/domain/."
    )
