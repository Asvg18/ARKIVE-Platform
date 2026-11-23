"""add interview_availability and job_requisitions.interview_durations

Revision ID: f4d9a2c6b815
Revises: e1c7b3a9d052
Create Date: 2026-10-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f4d9a2c6b815'
down_revision: Union[str, Sequence[str], None] = 'e1c7b3a9d052'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Interview scheduling, evaluator → HR → applicant (panel revision
    list, 15 Oct 2026, step 19b): the evaluator's free ranges per
    assigned round, and each job's saved interview length per round,
    which cuts those ranges into slots. Jobs made before this have no
    lengths saved and fall back to the editor's old defaults."""
    op.create_table(
        'interview_availability',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stage_instance_id', sa.Integer(), nullable=False),
        sa.Column('evaluator_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.String(length=10), nullable=False),
        sa.Column('start_time', sa.String(length=5), nullable=False),
        sa.Column('end_time', sa.String(length=5), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['evaluator_id'], ['users.id']),
        sa.ForeignKeyConstraint(['stage_instance_id'], ['stage_instances.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_interview_availability_stage_instance_id'),
        'interview_availability',
        ['stage_instance_id'],
        unique=False,
    )
    op.add_column('job_requisitions', sa.Column('interview_durations', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('job_requisitions', 'interview_durations')
    op.drop_index(op.f('ix_interview_availability_stage_instance_id'), table_name='interview_availability')
    op.drop_table('interview_availability')
