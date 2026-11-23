"""add interview round stage types and labels

Revision ID: 6ed3952ab2a9
Revises: 94c98bdb201e
Create Date: 2026-08-21 16:36:25.329499

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6ed3952ab2a9'
down_revision: Union[str, Sequence[str], None] = '94c98bdb201e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Evaluator redesign: interview_hr_director/interview_dept_head/
    interview_vp are being superseded by 6 generic, reusable
    interview_round_k slots — HR picks how many a given job needs and
    labels each one freely (interview_round_labels below), rather than
    every job being stuck with exactly 3 fixed, rigidly-named rounds.
    Postgres can't add an enum value inside the same transaction it might
    get used in, hence the autocommit block (same pattern as the
    'flagged' ApplicationStatus value in 94c98bdb201e).

    The legacy 3 values are NOT removed — Postgres can't drop enum values,
    and any already-in-flight application sitting on one of those stages
    keeps working untouched. New jobs simply stop being offered them."""
    with op.get_context().autocommit_block():
        for i in range(1, 7):
            op.execute(f"ALTER TYPE stage_type ADD VALUE IF NOT EXISTS 'interview_round_{i}'")
    op.add_column(
        "job_requisitions", sa.Column("interview_round_labels", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    """Postgres has no ALTER TYPE ... DROP VALUE — removing the 6 new
    stage_type values would mean rebuilding the enum type and every
    column that uses it. Not worth the risk for a dev-only downgrade
    path; this only reverses the (safe, reversible) column addition."""
    op.drop_column("job_requisitions", "interview_round_labels")
