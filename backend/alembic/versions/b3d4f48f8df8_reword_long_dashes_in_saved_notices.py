"""reword the long dashes in notices already sent

Revision ID: b3d4f48f8df8
Revises: c9e4b1d7a362
Create Date: 2026-10-17 00:00:00.000000

Revisions 2.0, phase 3 (17 Oct 2026). A notice's message is display text
ARKIVE wrote, so the long dashes come out of the ones already sent, in
the words the code now writes. Only ARKIVE's own wording changes: every
sentence ARKIVE has sent with a long dash, or with a typed double hyphen
standing in for one, is matched whole, and what was filled into it (a
name, a job title, a date, a note someone typed) is carried across
exactly as it was. A message that matches none of them is left alone.

The three interview rounds renamed in this phase ("Interview — Dept.
Head" became "Department Head Interview") are renamed wherever a notice
names them.

Downgrade puts the old sentences back. It leaves the three rounds'
names as they now are: "VP Interview" is also a name HR may have typed
for a round of its own, and a downgrade must not rename what someone
typed.
"""
import re
from typing import Callable, Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b3d4f48f8df8"
down_revision: Union[str, Sequence[str], None] = "c9e4b1d7a362"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_D = "\u2014"

#: The interview rounds renamed in phase 3, old name to new.
RENAMED_STAGES: dict[str, str] = {
    f"Interview {_D} HR Administrator": "HR Administrator Interview",
    f"Interview {_D} Dept. Head": "Department Head Interview",
    f"Interview {_D} VP": "VP Interview",
}

#: Every sentence ARKIVE has sent with a long dash (or " -- "), as it was
#: worded then and as the code words it now. A {slot} is what was filled
#: in, carried across unchanged. Module-level, like the backfill in
#: a7c3e9f15d28, so tests/test_notifications.py can check each one.
SENTENCES: tuple[tuple[str, str], ...] = (
    (
        f"HR denied your reschedule request {_D} the original schedule stands.",
        "HR denied your reschedule request. The original schedule stands.",
    ),
    (
        f"HR approved your reschedule request {_D} now set for {{when}}.",
        "HR approved your reschedule request. It's now set for {when}.",
    ),
    (
        f"Congratulations {_D} you've been selected for {{job}}.",
        "Congratulations, you've been selected for {job}.",
    ),
    (
        f"You've been shortlisted for {{job}} {_D} your application is moving forward.",
        "You've been shortlisted for {job}. Your application is moving forward.",
    ),
    (
        f"You've been shortlisted for {{job}} {_D} please confirm to continue.",
        "You've been shortlisted for {job}. Please confirm to continue.",
    ),
    (
        f"Your {{stage}} has been scheduled for {{when}} {_D} please confirm you can attend.",
        "Your {stage} has been scheduled for {when}. Please confirm you can attend.",
    ),
    (
        f"Pick a time for your {{stage}} {_D} {{count}} to choose from.",
        "Pick a time for your {stage}: {count} to choose from.",
    ),
    (
        f"{{who}} added their free times for {{whose}} {_D} ready to send to the applicant.",
        "{who} added their free times for {whose}, ready to send to the applicant.",
    ),
    (
        f"{{who}} did not respond within {{days}} days {_D} the offer has lapsed and the "
        "application is now withdrawn for {job}.",
        "{who} did not respond within {days} days, so the offer has lapsed and the "
        "application is now withdrawn for {job}.",
    ),
    # sent while exams had a waiting queue, until 15 Oct 2026
    (
        f"You're in a queue for {{stage}} {_D} every currently scheduled slot is full, {{rest}}",
        "You're in a queue for {stage}. Every currently scheduled slot is full, {rest}",
    ),
    (
        '{who} is not available for their {stage} on {when} -- "{note}"',
        '{who} is not available for their {stage} on {when}: "{note}"',
    ),
    (
        'None of the times sent work for {whose} -- "{note}"',
        'None of the times sent work for {whose}: "{note}"',
    ),
)


def _pattern(template: str) -> re.Pattern[str]:
    """A template as a whole-message pattern: its words exactly, each
    {slot} anything at all (as little as still lets the rest match)."""
    parts = re.split(r"\{(\w+)\}", template)
    return re.compile(
        "".join(re.escape(part) if i % 2 == 0 else f"(?P<{part}>.+?)" for i, part in enumerate(parts)),
        re.S,
    )


def _swap(message: str, before: str, after: str) -> str | None:
    match = _pattern(before).fullmatch(message)
    return after.format(**match.groupdict()) if match else None


def reworded(message: str) -> str:
    """A notice's message in today's wording: the renamed rounds, then the
    one sentence it is, if it is one of ARKIVE's."""
    for old, new in RENAMED_STAGES.items():
        message = message.replace(old, new)
    for before, after in SENTENCES:
        swapped = _swap(message, before, after)
        if swapped is not None:
            return swapped
    return message


def restored(message: str) -> str:
    """For downgrade: the sentence in its old wording again. The rounds'
    names stay (see the module docstring)."""
    for before, after in SENTENCES:
        swapped = _swap(message, after, before)
        if swapped is not None:
            return swapped
    return message


def renamed_title(title: str) -> str:
    """A title with the renamed rounds in it, renamed."""
    for old, new in RENAMED_STAGES.items():
        title = title.replace(old, new)
    return title


def rewrite_saved_notices(
    bind, message: Callable[[str], str], title: Callable[[str], str] = lambda value: value
) -> int:
    """Rewrites every saved notice through `message` (and its title through
    `title`), touching only the rows that change. Returns how many did."""
    notifications = sa.table(
        "notifications",
        sa.column("id", sa.Integer),
        sa.column("message", sa.Text),
        sa.column("title", sa.String),
    )
    changed = 0
    for row in bind.execute(sa.select(notifications.c.id, notifications.c.message, notifications.c.title)).all():
        new_message = message(row.message)
        new_title = title(row.title) if row.title is not None else None
        if new_message != row.message or new_title != row.title:
            bind.execute(
                notifications.update()
                .where(notifications.c.id == row.id)
                .values(message=new_message, title=new_title)
            )
            changed += 1
    return changed


def upgrade() -> None:
    rewrite_saved_notices(op.get_bind(), reworded, renamed_title)


def downgrade() -> None:
    rewrite_saved_notices(op.get_bind(), restored)
