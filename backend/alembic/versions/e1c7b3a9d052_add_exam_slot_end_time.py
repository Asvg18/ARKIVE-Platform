"""add exam_slots.end_time

Revision ID: e1c7b3a9d052
Revises: c2f8a4d61e93
Create Date: 2026-10-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e1c7b3a9d052'
down_revision: Union[str, Sequence[str], None] = 'c2f8a4d61e93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """An exam session is a time window, not a start time (panel revision
    list, 15 Oct 2026: "9:00–11:30, 1:00–4:30"). Nullable because the
    slots made before this have only a start time."""
    op.add_column('exam_slots', sa.Column('end_time', sa.String(length=5), nullable=True))


def downgrade() -> None:
    op.drop_column('exam_slots', 'end_time')
