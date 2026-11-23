"""add job description versions

Revision ID: c4e9a2f71b36
Revises: f7d2a9c4e815
Create Date: 2026-09-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e9a2f71b36'
down_revision: Union[str, Sequence[str], None] = 'f7d2a9c4e815'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """job_description_versions records every version of each job's
    description, so HR can replace one without losing what earlier
    applicants were scored against (see models/job_description_version).

    Every job that exists today gets its version 1 here, copied from the
    job's own columns. That is exact, not an approximation: until this
    revision no job's description could be changed, so the text a job
    holds now is the text every one of its applicants was scored against.
    No file is recorded for these -- the PDFs were never kept, only their
    names."""
    op.create_table(
        'job_description_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('requisition_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=True),
        sa.Column('stored_path', sa.String(length=512), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('qualifications', sa.Text(), nullable=True),
        sa.Column('requirements', sa.Text(), nullable=True),
        sa.Column('uploaded_by', sa.Integer(), nullable=True),
        sa.Column('change_note', sa.Text(), nullable=True),
        sa.Column('replaced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['requisition_id'], ['job_requisitions.id'], ),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('requisition_id', 'version'),
    )
    op.create_index(
        op.f('ix_job_description_versions_requisition_id'),
        'job_description_versions',
        ['requisition_id'],
        unique=False,
    )
    op.execute(
        """
        INSERT INTO job_description_versions
            (requisition_id, version, original_filename, description, qualifications,
             requirements, uploaded_by, created_at, updated_at)
        SELECT id, 1, jd_filename, description, qualifications,
               requirements, created_by, created_at, updated_at
        FROM job_requisitions
        """
    )


def downgrade() -> None:
    """Drops the history. The jobs' current text is untouched -- it lives on
    job_requisitions -- but earlier versions, and the record of who
    replaced what, are gone. Stored PDFs stay on disk, unreferenced."""
    op.drop_index(op.f('ix_job_description_versions_requisition_id'), table_name='job_description_versions')
    op.drop_table('job_description_versions')
