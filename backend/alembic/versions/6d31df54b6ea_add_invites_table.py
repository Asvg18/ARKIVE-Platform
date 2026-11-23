"""add invites table

Revision ID: 6d31df54b6ea
Revises: 6d0bfd8cefa7
Create Date: 2026-08-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6d31df54b6ea'
down_revision: Union[str, Sequence[str], None] = '6d0bfd8cefa7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """invites is how new hr_admin/evaluator accounts get provisioned —
    an HR admin invites an email+role, the invitee accepts via a
    single-use token and sets their own password. Replaces the old
    POST /hr/evaluators temp-password flow. role is a plain string, not
    the user_role Postgres enum (same reasoning as exam_slots.stage_type
    — no precedent for reusing an enum type across tables here)."""
    op.create_table(
        'invites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('invited_by_id', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['invited_by_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_invites_email'), 'invites', ['email'], unique=False)
    op.create_index(op.f('ix_invites_token_hash'), 'invites', ['token_hash'], unique=True)


def downgrade() -> None:
    """Safe, reversible table creation — nothing else depends on it."""
    op.drop_index(op.f('ix_invites_token_hash'), table_name='invites')
    op.drop_index(op.f('ix_invites_email'), table_name='invites')
    op.drop_table('invites')
