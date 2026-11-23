"""add invites.emailed_at

Revision ID: e6a3c9f1d7b2
Revises: b4e8c2f1a9d3
Create Date: 2026-09-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6a3c9f1d7b2'
down_revision: Union[str, Sequence[str], None] = 'b4e8c2f1a9d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """When each invitation's link last went out by email. Null for every
    invitation made before this -- nothing recorded whether those were
    emailed, and "not known to have been emailed" is the honest reading."""
    op.add_column('invites', sa.Column('emailed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('invites', 'emailed_at')
