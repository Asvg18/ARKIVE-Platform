"""add pre_screening_questions

Revision ID: a7d4e0f8c319
Revises: f3a8c1d92b47
Create Date: 2026-08-21 23:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7d4e0f8c319'
down_revision: Union[str, Sequence[str], None] = 'f3a8c1d92b47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """HR-editable AI Pre-Screening questions per job (pre-screening +
    exam-scheduling redesign) — kept as its own migration, separate from
    f3a8c1d92b47's examination_k stage types, since this is a logically
    distinct sub-feature (question authoring, not multi-exam scheduling)."""
    op.add_column(
        "job_requisitions", sa.Column("pre_screening_questions", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("job_requisitions", "pre_screening_questions")
