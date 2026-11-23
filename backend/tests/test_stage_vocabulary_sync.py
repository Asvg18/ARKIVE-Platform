"""The frontend's copy of the stage vocabulary must agree with this one.

frontend/src/shared/lib/stageLabels.ts restates three things the backend
already knows: which stage types exist, which are interviews, and which
are examinations. Two copies of one fact, kept in step by hand.

**Why a test, not an endpoint.** The obvious fix is serving the
vocabulary from the API and deleting the frontend's copy -- bad trade
here. The stage list changes roughly never (adding one is a Postgres
enum migration rewriting every job's workflow), while an endpoint would
put a network round-trip, a loading state, and an offline-failure mode
in front of *every* screen that renders a stage name. The cost of
duplication is drift; drift is what a test can make impossible.

If this test fails, the frontend file is the one to change -- the
Python enum and dfa.py are the source of truth.

Parses the TypeScript with regular expressions rather than running
Node -- enough for the three literal declarations it reads, and it
means the backend suite has no dependency on the frontend's toolchain
being installed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.domain.dfa import is_exam_stage, is_interview_stage
from app.models.enums import ApplicationStatus, StageType

STAGE_LABELS_TS = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "shared" / "lib" / "stageLabels.ts"
)


def _record_keys(source: str, const_name: str) -> set[str]:
    """The keys of an exported `Record<string, string>` object literal."""
    match = re.search(
        rf"export const {const_name}: Record<string, string> = \{{(.*?)\n\}};",
        source,
        re.S,
    )
    assert match, f"{const_name} not found in {STAGE_LABELS_TS.name} — was it renamed?"
    body = re.sub(r"//[^\n]*", "", match.group(1))
    return set(re.findall(r"^\s*(\w+):", body, re.M))


@pytest.fixture(scope="module")
def ts_source() -> str:
    if not STAGE_LABELS_TS.exists():
        pytest.skip(f"frontend source not present at {STAGE_LABELS_TS}")
    return STAGE_LABELS_TS.read_text()


def test_every_stage_type_has_a_frontend_label(ts_source: str) -> None:
    """A stage with no label renders as its raw enum value — readable, but
    it looks like a bug to HR and reads badly in a demo."""
    missing = sorted({s.value for s in StageType} - _record_keys(ts_source, "STAGE_LABELS"))
    assert not missing, (
        f"StageType values with no entry in STAGE_LABELS: {missing}. "
        f"Add them to {STAGE_LABELS_TS.name}."
    )


def test_the_frontend_invents_no_stages_of_its_own(ts_source: str) -> None:
    """A label for a stage the backend cannot produce is dead code at best,
    and at worst a stage someone believes exists."""
    extra = sorted(_record_keys(ts_source, "STAGE_LABELS") - {s.value for s in StageType})
    assert not extra, f"STAGE_LABELS keys that are not StageType values: {extra}"


def _record_entries(source: str, const_name: str) -> dict[str, str]:
    """The key/value pairs of an exported `Record<string, string>` object
    literal whose values are plain double-quoted strings."""
    match = re.search(
        rf"export const {const_name}: Record<string, string> = \{{(.*?)\n\}};",
        source,
        re.S,
    )
    assert match, f"{const_name} not found in {STAGE_LABELS_TS.name}. Was it renamed?"
    body = re.sub(r"//[^\n]*", "", match.group(1))
    return dict(re.findall(r'^\s*(\w+):\s*"([^"]*)",?\s*$', body, re.M))


def test_both_lists_give_every_stage_the_same_name(ts_source: str) -> None:
    """Each stage's default name is written twice, here and in the
    frontend, and a rename has to land in both: revisions 2.0 (phase 3)
    renamed the three fixed interview rounds, "Interview — Dept. Head"
    becoming "Department Head Interview". A stage called one thing on a
    screen and another in a notice or an email is the drift this stops."""
    from app.services.stage_labels import _DEFAULT_LABELS

    assert _record_entries(ts_source, "STAGE_LABELS") == _DEFAULT_LABELS


def test_every_application_status_has_a_frontend_label(ts_source: str) -> None:
    missing = sorted({s.value for s in ApplicationStatus} - _record_keys(ts_source, "STATUS_LABELS"))
    assert not missing, f"ApplicationStatus values with no entry in STATUS_LABELS: {missing}"


@pytest.mark.parametrize("stage", [s.value for s in StageType], ids=[s.value for s in StageType])
def test_the_two_classifications_agree(stage: str) -> None:
    """`isInterviewStage`/`isExamStage` in stageLabels.ts are prefix rules
    copied from `app/domain/dfa.py`. A stage the frontend classifies
    differently from the server produces a screen that disagrees with the
    record behind it — an interview round whose scorecard never appears, or
    an exam whose score entry is missing.

    The rules are re-implemented here from the TypeScript's own logic
    (`startsWith("interview_")` and `startsWith("examination")`) rather than
    parsed, because a prefix test is small enough that restating it is
    clearer than extracting it.
    """
    assert stage.startswith("interview_") == is_interview_stage(stage)
    assert stage.startswith("examination") == is_exam_stage(stage)
