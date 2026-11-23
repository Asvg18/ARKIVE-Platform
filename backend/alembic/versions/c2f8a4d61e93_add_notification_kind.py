"""add notifications.kind

Revision ID: c2f8a4d61e93
Revises: 5b8e2d7c9f14
Create Date: 2026-10-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c2f8a4d61e93'
down_revision: Union[str, Sequence[str], None] = '5b8e2d7c9f14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """What each notice is about, for the Notifications page's filter
    (panel revision list, 15 Oct 2026).

    Notices already sent carry no kind, so they are sorted by the wording
    each notify() call has always used -- a best effort that only affects
    which filter an old notice shows under; anything unmatched stays
    "system" and still shows under All."""
    op.add_column(
        'notifications',
        sa.Column('kind', sa.String(length=20), nullable=False, server_default='system'),
    )
    op.execute(
        """
        UPDATE notifications SET kind = 'schedule'
        WHERE message ILIKE '%has been scheduled for%'
           OR message ILIKE '%requested to reschedule%'
           OR message ILIKE '%reschedule request%'
           OR message ILIKE '%is not available for their%'
           OR message ILIKE '%assigned to conduct%'
           OR message ILIKE '%in a queue for%'
        """
    )
    op.execute(
        """
        UPDATE notifications SET kind = 'decision'
        WHERE kind = 'system'
          AND (message ILIKE '%shortlisted%'
            OR message ILIKE '%you''ve been selected%'
            OR message ILIKE '%decided not to move forward%'
            OR message ILIKE '%has been reopened%'
            OR message ILIKE '%the offer%'
            OR message ILIKE '%an update on your application%')
        """
    )
    op.execute(
        """
        UPDATE notifications SET kind = 'application'
        WHERE kind = 'system'
          AND (message ILIKE '%has been recorded for%'
            OR message ILIKE '%closed to new applicants%')
        """
    )


def downgrade() -> None:
    op.drop_column('notifications', 'kind')
