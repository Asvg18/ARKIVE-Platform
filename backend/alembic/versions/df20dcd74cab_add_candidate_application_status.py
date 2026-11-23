"""add candidate application status

Revision ID: df20dcd74cab
Revises: 5510227261a5
Create Date: 2026-08-11 21:48:45.753677

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'df20dcd74cab'
down_revision: Union[str, Sequence[str], None] = '5510227261a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


application_status_enum = sa.Enum(
    "active", "rejected", "hired", name="application_status"
)


def upgrade() -> None:
    """Add CandidateApplication.status (hire/reject outcome), decoupled
    from current_stage/the DFA. Unlike create_table, add_column does not
    auto-create an enum type, so it's created explicitly first."""
    application_status_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "candidate_applications",
        sa.Column(
            "status",
            application_status_enum,
            nullable=False,
            server_default="active",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("candidate_applications", "status")
    application_status_enum.drop(op.get_bind(), checkfirst=True)
