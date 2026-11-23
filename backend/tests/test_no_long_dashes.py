"""No long dash in any text ARKIVE shows a person (revisions 2.0, phase
3, 17 Oct 2026). Aerron: it "looks AI".

Every string literal in app/ is read with Python's own parser, so
comments and docstrings, which nobody using ARKIVE reads, are passed
over. The short dash is fine: it marks ranges and empty values.

The one place a long dash stays is text an AI step is sent: its
instructions, and the facts the Decision Brief is given. Those are kept
exactly as they are (Aerron, 17 Oct), and test_ai_instruction_lock.py
records their exact wording in ai_instruction_lock.json. A literal is let
through only when it is really part of that recorded text, so a sentence
a person sees cannot hide behind it. The frontend has the same check
(frontend/src/noLongDashes.test.ts).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
LOCK_FILE = Path(__file__).with_name("ai_instruction_lock.json")
LONG_DASH = "\u2014"


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in _strings(item)]
    return []


def _text_the_ai_is_sent() -> list[str]:
    return _strings(json.loads(LOCK_FILE.read_text(encoding="utf-8")))


def _docstrings(tree: ast.AST) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                found.add(id(first.value))
    return found


def _dashed_literals(source: str, ai_text: list[str]) -> list[tuple[int, str]]:
    """(line, text) of every string literal in `source` with a long dash
    that is neither a docstring nor a piece of what an AI step is sent.
    A piece has to have words in it: a bare dash is in every prompt."""
    tree = ast.parse(source)
    docstrings = _docstrings(tree)
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)) or id(node) in docstrings:
            continue
        text = node.value
        if LONG_DASH not in text:
            continue
        if any(ch.isalpha() for ch in text) and any(text in sent for sent in ai_text):
            continue
        found.append((node.lineno, text))
    return sorted(found)


def test_a_long_dash_is_found_in_strings_but_not_in_comments_or_docstrings() -> None:
    sample = (
        f'"""A module docstring {LONG_DASH} fine."""\n'
        f"# a comment {LONG_DASH} fine\n"
        f'MESSAGE = "Couldn\'t read it {LONG_DASH} try again."\n'
        f'LABEL = f"{{name}} {LONG_DASH} {{job}}"\n'
        f'PROMPT = "Read every line {LONG_DASH} carefully."\n'
        f'EMPTY = "{LONG_DASH}"\n'
    )
    prompts = [f"You are a reviewer. Read every line {LONG_DASH} carefully. Then answer."]
    assert [line for line, _ in _dashed_literals(sample, prompts)] == [3, 4, 6]


def test_the_ai_text_on_record_is_there_to_check_against() -> None:
    # an empty lock would let every dash through as "AI text"
    assert any(LONG_DASH in text for text in _text_the_ai_is_sent())


def test_no_text_a_person_sees_has_a_long_dash() -> None:
    ai_text = _text_the_ai_is_sent()
    offenders = [
        f"{path.relative_to(APP_DIR.parent)}:{line}  {text.strip()[:80]!r}"
        for path in sorted(APP_DIR.rglob("*.py"))
        for line, text in _dashed_literals(path.read_text(encoding="utf-8"), ai_text)
    ]
    assert not offenders, (
        "Long dashes in text people see. Reword them by meaning (a comma, period, "
        "colon or brackets):\n" + "\n".join(offenders)
    )
