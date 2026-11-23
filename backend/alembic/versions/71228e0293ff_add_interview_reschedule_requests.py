"""add interview reschedule requests

Revision ID: 71228e0293ff
Revises: ba5e5f917c1c
Create Date: 2026-08-21 17:48:39.009193

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '71228e0293ff'
down_revision: Union[str, Sequence[str], None] = 'ba5e5f917c1c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Evaluator redesign, part 3: an evaluator's request to move a
    scheduled interview they're assigned to, reviewed by HR. A new table
    (not StageInstance.payload) since a request has its own lifecycle
    independent of the schedule itself — see the model's docstring.

    The enum type is created implicitly by create_table's column
    definition below (create_type defaults to True) — no separate
    .create() call, which would double-create it in the same transaction."""
    reschedule_status = sa.Enum(
        "pending", "approved", "denied", name="reschedule_request_status"
    )

    op.create_table(
        "interview_reschedule_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "stage_instance_id", sa.Integer(), sa.ForeignKey("stage_instances.id"), nullable=False
        ),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("proposed_date", sa.String(length=10), nullable=False),
        sa.Column("proposed_time", sa.String(length=5), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", reschedule_status, nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("interview_reschedule_requests")
    sa.Enum(name="reschedule_request_status").drop(op.get_bind())
