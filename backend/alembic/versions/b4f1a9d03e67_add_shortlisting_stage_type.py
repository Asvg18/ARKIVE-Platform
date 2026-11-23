"""add shortlisting stage type

Revision ID: b4f1a9d03e67
Revises: 6d31df54b6ea
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4f1a9d03e67'
down_revision: Union[str, Sequence[str], None] = '6d31df54b6ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """A single fixed stage, not a _k family like examinations/interview
    rounds -- HR marks a candidate shortlisted or not once, so it needs
    no per-job relabeling column of its own (same reasoning as
    reference_check/background_check). Postgres can't add an enum value
    inside the same transaction it might get used in, hence the
    autocommit block -- same pattern as every prior stage_type addition
    (94c98bdb201e, 6ed3952ab2a9, f3a8c1d92b47)."""
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE stage_type ADD VALUE IF NOT EXISTS 'shortlisting'")


def downgrade() -> None:
    """Postgres has no ALTER TYPE ... DROP VALUE -- same irreversibility
    as every other stage_type addition in this project. Nothing else was
    added in this revision to reverse."""
    pass
