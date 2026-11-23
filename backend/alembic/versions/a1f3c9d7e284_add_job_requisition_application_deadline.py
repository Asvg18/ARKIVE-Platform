"""add job requisition application_deadline field

Revision ID: a1f3c9d7e284
Revises: de8267f5d921
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f3c9d7e284'
down_revision: Union[str, Sequence[str], None] = 'de8267f5d921'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add JobRequisition.application_deadline — nullable since every
    requisition created before this field existed (including drafts) never
    had one; required to publish, enforced at the schema layer, not the DB."""
    op.add_column('job_requisitions', sa.Column('application_deadline', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('job_requisitions', 'application_deadline')
