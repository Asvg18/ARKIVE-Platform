"""add examination stage types and labels

Revision ID: f3a8c1d92b47
Revises: c250bf3eb41f
Create Date: 2026-08-21 23:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a8c1d92b47'
down_revision: Union[str, Sequence[str], None] = 'c250bf3eb41f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Pre-screening + exam-scheduling redesign: the plain `examination`
    stage type stays as the legacy singular slot, but jobs that need 2+
    independent exams (e.g. "Technical Exam" + "Aptitude Exam") now get 4
    generic, reusable examination_k slots — same pattern as the evaluator
    redesign's interview_round_1..6 (6ed3952ab2a9). Postgres can't add an
    enum value inside the same transaction it might get used in, hence the
    autocommit block (same pattern used there and in 94c98bdb201e)."""
    with op.get_context().autocommit_block():
        for i in range(1, 5):
            op.execute(f"ALTER TYPE stage_type ADD VALUE IF NOT EXISTS 'examination_{i}'")
    op.add_column(
        "job_requisitions", sa.Column("examination_labels", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    """Postgres has no ALTER TYPE ... DROP VALUE — this only reverses the
    (safe, reversible) column addition, same as 6ed3952ab2a9."""
    op.drop_column("job_requisitions", "examination_labels")
