"""add additional_sections to job requisitions and their versions

Revision ID: a7d4e2b9c1f6
Revises: cf4753c3faab
Create Date: 2026-10-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7d4e2b9c1f6'
down_revision: Union[str, Sequence[str], None] = 'cf4753c3faab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """The parts of a job description the three fixed fields have no
    place for (salary, benefits, documents to submit...), as
    [{title, content}] -- on the job, and frozen on each version.

    server_default '[]' so every job and version stored before this reads
    as "no extra sections" rather than NULL, which the read schemas would
    reject."""
    op.add_column(
        'job_requisitions',
        sa.Column('additional_sections', sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )
    op.add_column(
        'job_description_versions',
        sa.Column('additional_sections', sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('job_description_versions', 'additional_sections')
    op.drop_column('job_requisitions', 'additional_sections')
