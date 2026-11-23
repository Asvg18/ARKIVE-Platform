"""score résumés from the reviewed form, not the PDF text

Revision ID: 5b8e2d7c9f14
Revises: a7d4e2b9c1f6
Create Date: 2026-10-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '5b8e2d7c9f14'
down_revision: Union[str, Sequence[str], None] = 'a7d4e2b9c1f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drops every cached résumé embedding.

    Each one was computed from the PDF's raw text, and the match score
    now reads the reviewed form instead (_resume_scoring_text in
    services/skill_matching.py). A kept vector would be reused the next
    time that résumé is scored -- the pre-screening retry after a failed
    upload-time score -- and mix the old source into a new score. The
    vectors are derived data: the next scoring recomputes one from the
    form, so nothing is lost but one embeddings call.

    Not touched: the scores already stored on skill_matching stage
    payloads. Re-deriving them needs a model call, which a migration must
    not make, so they stay the scores those applications were given."""
    op.execute("UPDATE application_resumes SET embedding = NULL")


def downgrade() -> None:
    """The same statement: a vector computed from the form is just as
    wrong for the older code, which embeds the raw text."""
    op.execute("UPDATE application_resumes SET embedding = NULL")
