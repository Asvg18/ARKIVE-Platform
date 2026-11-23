"""add job requisition JD-upload fields

Revision ID: de8267f5d921
Revises: 2378ba4d9dde
Create Date: 2026-08-13 09:43:02.763831

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'de8267f5d921'
down_revision: Union[str, Sequence[str], None] = '2378ba4d9dde'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add JobRequisition.qualifications/requirements/jd_filename — nullable
    since every requisition created before the Job Opening Builder's
    JD-upload flow (including the seed demo jobs) never had one."""
    op.add_column('job_requisitions', sa.Column('qualifications', sa.Text(), nullable=True))
    op.add_column('job_requisitions', sa.Column('requirements', sa.Text(), nullable=True))
    op.add_column('job_requisitions', sa.Column('jd_filename', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('job_requisitions', 'jd_filename')
    op.drop_column('job_requisitions', 'requirements')
    op.drop_column('job_requisitions', 'qualifications')
