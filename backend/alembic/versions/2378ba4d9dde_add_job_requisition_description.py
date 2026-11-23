"""add job requisition description

Revision ID: 2378ba4d9dde
Revises: df20dcd74cab
Create Date: 2026-08-12 12:43:08.779377

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2378ba4d9dde'
down_revision: Union[str, Sequence[str], None] = 'df20dcd74cab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add JobRequisition.description — nullable since the two existing
    demo requisitions predate the Job Opening Builder and never had one."""
    op.add_column(
        "job_requisitions",
        sa.Column("description", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("job_requisitions", "description")
