"""remove the staff email rule's outside-evaluator flags

Revision ID: cf4753c3faab
Revises: 9c2e5b7a4d18
Create Date: 2026-10-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf4753c3faab'
down_revision: Union[str, Sequence[str], None] = '9c2e5b7a4d18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """The staff email rule is out of ARKIVE's scope (decided 1 Oct
    2026): staff accounts, like applicants, need only a valid email
    address. users.is_external and invites.external recorded the one
    exemption from that rule -- an evaluator invited "from outside the
    organization" -- and mean nothing without it."""
    op.drop_column('invites', 'external')
    op.drop_column('users', 'is_external')


def downgrade() -> None:
    """Brings the columns back as false everywhere: which evaluators were
    from outside is not kept anywhere else to restore it from."""
    op.add_column(
        'users',
        sa.Column('is_external', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
    op.add_column(
        'invites',
        sa.Column('external', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
