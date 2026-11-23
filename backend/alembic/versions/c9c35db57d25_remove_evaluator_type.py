"""remove evaluator type

Revision ID: c9c35db57d25
Revises: 78c492ee08a3
Create Date: 2026-08-21 18:31:07.413287

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9c35db57d25'
down_revision: Union[str, Sequence[str], None] = '78c492ee08a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Evaluator redesign, final step: evaluator accounts are no longer
    categorized by a fixed type (dept_head/vp) — real per-job, per-
    candidate assignment (requisition_evaluators, StageInstance.
    assigned_evaluator_id) replaced what this column used to gate. Done
    last, only after every reader in the codebase was confirmed gone."""
    op.drop_column("users", "evaluator_type")
    op.execute("DROP TYPE evaluator_type")


def downgrade() -> None:
    """Lossy: re-creates the column but can't recover which evaluator had
    which type — matches this codebase's existing precedent for a lossy
    downgrade (5510227261a5's role collapse) on a dev-only rollback path."""
    evaluator_type = sa.Enum("dept_head", "vp", name="evaluator_type")
    evaluator_type.create(op.get_bind())
    op.add_column("users", sa.Column("evaluator_type", evaluator_type, nullable=True))
