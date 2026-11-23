"""add notification sender, title, application and archive

Revision ID: a7c3e9f15d28
Revises: f4d9a2c6b815
Create Date: 2026-10-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a7c3e9f15d28'
down_revision: Union[str, Sequence[str], None] = 'f4d9a2c6b815'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Module-level so tests/test_notifications.py can run the backfill on a
# notice of its own and check what it does.
TITLE_BACKFILL = """
    UPDATE notifications SET title = CASE kind
        WHEN 'schedule' THEN 'Schedule update'
        WHEN 'decision' THEN 'Decision update'
        WHEN 'application' THEN 'Application update'
        ELSE 'Notice'
    END
    WHERE title IS NULL
"""
APPLICATION_BACKFILL = (
    # HR's and the applicant's links name the application itself...
    """
    UPDATE notifications n SET application_id = a.id
    FROM candidate_applications a
    WHERE n.application_id IS NULL
      AND (n.link LIKE '/hr/applications/%' OR n.link LIKE '/applicant/applications/%')
      AND a.id = substring(n.link FROM '^/[a-z]+/applications/([0-9]+)')::int
    """,
    # ...an evaluator's names the interview round, which belongs to one.
    """
    UPDATE notifications n SET application_id = s.application_id
    FROM stage_instances s
    WHERE n.application_id IS NULL
      AND n.link LIKE '/evaluator/interviews/%'
      AND s.id = substring(n.link FROM '^/evaluator/interviews/([0-9]+)')::int
    """,
)


def upgrade() -> None:
    """The notifications inbox (revisions 2.0, 16 Oct 2026): who a notice
    came from, a short subject, the application it is about, and an
    archive. Notices already sent get a subject from their kind and the
    application their link points at; they get no sender, since nothing
    recorded who acted, so they show their kind's icon instead."""
    op.add_column('notifications', sa.Column('actor_id', sa.Integer(), nullable=True))
    op.add_column('notifications', sa.Column('title', sa.String(length=120), nullable=True))
    op.add_column('notifications', sa.Column('application_id', sa.Integer(), nullable=True))
    op.add_column('notifications', sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        'notifications_actor_id_fkey', 'notifications', 'users', ['actor_id'], ['id']
    )
    op.create_foreign_key(
        'notifications_application_id_fkey',
        'notifications',
        'candidate_applications',
        ['application_id'],
        ['id'],
    )
    op.create_index('ix_notifications_user_id_id', 'notifications', ['user_id', 'id'])

    op.execute(TITLE_BACKFILL)
    for statement in APPLICATION_BACKFILL:
        op.execute(statement)
    op.alter_column('notifications', 'title', nullable=False)


def downgrade() -> None:
    op.drop_index('ix_notifications_user_id_id', table_name='notifications')
    op.drop_constraint('notifications_application_id_fkey', 'notifications', type_='foreignkey')
    op.drop_constraint('notifications_actor_id_fkey', 'notifications', type_='foreignkey')
    op.drop_column('notifications', 'archived_at')
    op.drop_column('notifications', 'application_id')
    op.drop_column('notifications', 'title')
    op.drop_column('notifications', 'actor_id')
