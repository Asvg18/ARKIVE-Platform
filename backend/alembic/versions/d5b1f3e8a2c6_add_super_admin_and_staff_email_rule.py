"""add super admin, outside evaluators, and setup invitations

Revision ID: d5b1f3e8a2c6
Revises: a7d3e1f09c52
Create Date: 2026-09-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5b1f3e8a2c6'
down_revision: Union[str, Sequence[str], None] = 'a7d3e1f09c52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Three things staff account management was missing.

    - users.is_super_admin: only super admins manage accounts now.
      **Every HR admin that already exists becomes one**, because until
      this migration every HR admin *could* manage accounts -- taking
      that away from all of them at once would leave an installation
      with nobody able to open User Management. A super admin can remove
      it from whoever should not have it.
    - users.is_external / invites.external: an evaluator invited from
      outside the organization, allowed an email outside the staff
      domains.
    - invites.invited_by_id becomes nullable, and invites.super_admin is
      added: the first-admin setup step sends an invitation that nobody
      sent, for a super admin account."""
    op.add_column(
        'users',
        sa.Column('is_super_admin', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
    op.add_column(
        'users',
        sa.Column('is_external', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
    op.execute("UPDATE users SET is_super_admin = true WHERE role = 'hr_admin'")

    op.add_column(
        'invites',
        sa.Column('super_admin', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
    op.add_column(
        'invites',
        sa.Column('external', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
    op.alter_column('invites', 'invited_by_id', existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    """Reversible, with one loss: setup invitations have no sender, and
    the column cannot become required again while they exist, so they
    are deleted. An account already created from one is untouched."""
    op.execute("DELETE FROM invites WHERE invited_by_id IS NULL")
    op.alter_column('invites', 'invited_by_id', existing_type=sa.Integer(), nullable=False)
    op.drop_column('invites', 'external')
    op.drop_column('invites', 'super_admin')
    op.drop_column('users', 'is_external')
    op.drop_column('users', 'is_super_admin')
