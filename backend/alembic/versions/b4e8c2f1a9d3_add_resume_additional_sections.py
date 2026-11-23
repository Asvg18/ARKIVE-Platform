"""add application_resumes.additional_sections

Revision ID: b4e8c2f1a9d3
Revises: d5b1f3e8a2c6
Create Date: 2026-09-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4e8c2f1a9d3'
down_revision: Union[str, Sequence[str], None] = 'd5b1f3e8a2c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Résumé sections the fixed fields have no place for (projects,
    awards, organizations...), as [{title, content}].

    server_default '[]' so every résumé stored before this reads as "no
    extra sections" rather than NULL, which the read schema would
    reject."""
    op.add_column(
        'application_resumes',
        sa.Column('additional_sections', sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('application_resumes', 'additional_sections')
