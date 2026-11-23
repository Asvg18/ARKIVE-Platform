"""add notifications table

Revision ID: 78c492ee08a3
Revises: 71228e0293ff
Create Date: 2026-08-21 18:06:11.988041

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '78c492ee08a3'
down_revision: Union[str, Sequence[str], None] = '71228e0293ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Evaluator redesign, part 4: minimal in-app notifications — an
    evaluator being assigned a round, a reschedule request being raised,
    and its resolution. Deliberately simple (fetch-on-load, no real-time
    push) — see the model's docstring."""
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("link", sa.String(length=255), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("notifications")
