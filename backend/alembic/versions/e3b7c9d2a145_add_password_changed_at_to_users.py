"""add password_changed_at to users

Revision ID: e3b7c9d2a145
Revises: c8a2e5f41b90
Create Date: 2026-09-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3b7c9d2a145'
down_revision: Union[str, Sequence[str], None] = 'c8a2e5f41b90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Records when an account's password last changed, so a session
    that began before that moment can be refused.

    Without it, changing or resetting a password left every session
    already open on the old one working until its token expired — which
    is exactly backwards on the reset path, where the reason someone
    resets is that they think another person is in their account.

    Nullable, and deliberately not backfilled to now(): null means
    "never changed since the account was created", i.e. nothing to
    measure a session against. Backfilling would instead mean "every
    password changed this instant" and would sign out every existing
    session the moment this deployed, for no security benefit."""
    op.add_column(
        'users',
        sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Reversible: sessions simply stop being measured against a password
    change again."""
    op.drop_column('users', 'password_changed_at')
