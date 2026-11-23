"""add withdrawn status and application documents table

Revision ID: 6d0bfd8cefa7
Revises: 6c8957b4b0e0
Create Date: 2026-08-23 11:42:15.770036

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6d0bfd8cefa7'
down_revision: Union[str, Sequence[str], None] = '6c8957b4b0e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """'withdrawn' is a new CandidateApplication.status outcome — Phase 7's
    "Cancel Application" (docs/ARKIVE-implementation-roadmap.md), applicant-
    initiated, distinct from HR's 'rejected'. Same autocommit-block
    requirement as the 'flagged' status migration (94c98bdb201e) — Postgres
    can't add an enum value inside the same transaction it might get used in.

    application_documents is Phase 7's other half, "Add More Documents" —
    supplemental files (reference letters, an updated portfolio, etc.) an
    applicant attaches after their initial document_upload submission,
    any number of them, distinct from the single required
    application_resumes row."""
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE application_status ADD VALUE IF NOT EXISTS 'withdrawn'")

    op.create_table(
        'application_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('stored_path', sa.String(length=512), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['candidate_applications.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Postgres has no ALTER TYPE ... DROP VALUE — same reasoning as
    94c98bdb201e's downgrade. Only the (safe, reversible) table creation
    is undone."""
    op.drop_table('application_documents')
