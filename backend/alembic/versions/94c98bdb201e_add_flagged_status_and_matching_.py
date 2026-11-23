"""add flagged status and matching embeddings

Revision ID: 94c98bdb201e
Revises: a8905b1fbf1c
Create Date: 2026-08-21 10:19:17.986570

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '94c98bdb201e'
down_revision: Union[str, Sequence[str], None] = 'a8905b1fbf1c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """'flagged' is a new CandidateApplication.status outcome — the real
    Skill Matching Agent found the candidate isn't a strong enough fit for
    the job they applied to, but the system doesn't auto-reject; it stops
    the DFA at skill_matching and waits for HR to decide (see
    POST /hr/applications/{id}/resolve-flag). Postgres can't add an enum
    value inside the same transaction it might get used in, hence the
    autocommit block.

    embedding columns cache each side's OpenAI embedding (JSON list[float])
    so scoring a resume against every open requisition doesn't mean
    re-embedding every requisition's JD on every submission — a
    requisition's JD text never changes after creation, so its embedding is
    computed once and reused; a resume's embedding is computed once at
    document-upload submission time."""
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE application_status ADD VALUE IF NOT EXISTS 'flagged'")
    op.add_column('job_requisitions', sa.Column('embedding', sa.JSON(), nullable=True))
    op.add_column('application_resumes', sa.Column('embedding', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Postgres has no ALTER TYPE ... DROP VALUE — removing 'flagged' from
    application_status would require rebuilding the enum type and every
    column/index that uses it. Not worth the risk for a dev-only downgrade
    path; this only reverses the (safe, reversible) column additions."""
    op.drop_column('application_resumes', 'embedding')
    op.drop_column('job_requisitions', 'embedding')
