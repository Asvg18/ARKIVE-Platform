"""add requisition evaluators and assignment

Revision ID: ba5e5f917c1c
Revises: 6ed3952ab2a9
Create Date: 2026-08-21 17:02:02.185767

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ba5e5f917c1c'
down_revision: Union[str, Sequence[str], None] = '6ed3952ab2a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Evaluator redesign, part 2: requisition_evaluators is a job's pool
    of evaluators eligible to conduct its interview rounds; a real
    assignment (StageInstance.assigned_evaluator_id) is a separate step
    HR takes per candidate per round. This is what replaces the old
    evaluator_type-based blanket visibility (every evaluator of a type
    saw every instance of that type, system-wide) with real per-
    candidate assignment."""
    op.create_table(
        "requisition_evaluators",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "requisition_id",
            sa.Integer(),
            sa.ForeignKey("job_requisitions.id"),
            nullable=False,
        ),
        sa.Column("evaluator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.UniqueConstraint("requisition_id", "evaluator_id"),
    )
    op.add_column("stage_instances", sa.Column("assigned_evaluator_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_stage_instances_assigned_evaluator_id_users",
        "stage_instances",
        "users",
        ["assigned_evaluator_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_stage_instances_assigned_evaluator_id_users", "stage_instances", type_="foreignkey"
    )
    op.drop_column("stage_instances", "assigned_evaluator_id")
    op.drop_table("requisition_evaluators")
