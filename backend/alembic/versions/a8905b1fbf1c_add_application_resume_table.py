"""add application resume table

Revision ID: a8905b1fbf1c
Revises: a1f3c9d7e284
Create Date: 2026-08-20 22:25:35.544147

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8905b1fbf1c'
down_revision: Union[str, Sequence[str], None] = 'a1f3c9d7e284'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create application_resumes — the standardized, 1:1-with-application
    resume record (real uploaded file + GPT-4o-mini-normalized structured
    fields + raw extracted text for future BM25 use). Replaces the old
    convention of a typed-by-hand resume_filename string living in
    StageInstance.payload for the document_upload stage."""
    op.create_table(
        'application_resumes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('stored_path', sa.String(length=512), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=64), nullable=False),
        sa.Column('location', sa.String(length=255), nullable=False),
        sa.Column('linkedin_url', sa.String(length=512), nullable=False),
        sa.Column('portfolio_url', sa.String(length=512), nullable=False),
        sa.Column('professional_summary', sa.Text(), nullable=False),
        sa.Column('education', sa.JSON(), nullable=False),
        sa.Column('experience', sa.JSON(), nullable=False),
        sa.Column('skills', sa.JSON(), nullable=False),
        sa.Column('certifications', sa.JSON(), nullable=False),
        sa.Column('raw_extracted_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['candidate_applications.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('application_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('application_resumes')
