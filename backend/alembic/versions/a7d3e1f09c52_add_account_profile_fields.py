"""add account profile fields and email change tokens

Revision ID: a7d3e1f09c52
Revises: c4e9a2f71b36
Create Date: 2026-09-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7d3e1f09c52'
down_revision: Union[str, Sequence[str], None] = 'c4e9a2f71b36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Account Settings: a profile photo, and a job title and department
    for staff, on the users row; and email_change_tokens, the pending
    "confirm your new sign-in email" links.

    All three new columns are nullable and left empty -- an account
    without a photo shows initials, exactly as every account did before
    this. Only the SHA-256 digest of each email-change token is stored,
    the discipline password_reset_tokens already follows."""
    op.add_column('users', sa.Column('avatar_file', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('job_title', sa.String(length=120), nullable=True))
    op.add_column('users', sa.Column('department', sa.String(length=120), nullable=True))

    op.create_table(
        'email_change_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('new_email', sa.String(length=320), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_email_change_tokens_user_id'), 'email_change_tokens', ['user_id'], unique=False)
    op.create_index(op.f('ix_email_change_tokens_token_hash'), 'email_change_tokens', ['token_hash'], unique=True)


def downgrade() -> None:
    """Reversible. Photos already uploaded stay on disk under
    uploads/avatars but are no longer referenced."""
    op.drop_index(op.f('ix_email_change_tokens_token_hash'), table_name='email_change_tokens')
    op.drop_index(op.f('ix_email_change_tokens_user_id'), table_name='email_change_tokens')
    op.drop_table('email_change_tokens')
    op.drop_column('users', 'department')
    op.drop_column('users', 'job_title')
    op.drop_column('users', 'avatar_file')
