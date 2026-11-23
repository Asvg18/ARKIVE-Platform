"""collapse user roles to hr_admin

Revision ID: 5510227261a5
Revises: a70ef31260f1
Create Date: 2026-08-11 21:44:07.079978

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5510227261a5'
down_revision: Union[str, Sequence[str], None] = 'a70ef31260f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Collapse UserRole from 4 values (applicant/hr_director/evaluator/admin)
    to 3 (applicant/hr_admin/evaluator) — hr_director and admin merge into
    a single hr_admin. Postgres has no ALTER TYPE ... DROP VALUE, so the
    only way to actually remove the retired values (not just stop using
    them) is: rename the old type out of the way, create the new type,
    swap the column over with a USING mapping, then drop the old type."""
    op.execute("ALTER TYPE user_role RENAME TO user_role_old")
    op.execute("CREATE TYPE user_role AS ENUM ('applicant', 'hr_admin', 'evaluator')")
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN role TYPE user_role
        USING (
            CASE role::text
                WHEN 'hr_director' THEN 'hr_admin'
                WHEN 'admin' THEN 'hr_admin'
                ELSE role::text
            END
        )::user_role
        """
    )
    op.execute("DROP TYPE user_role_old")


def downgrade() -> None:
    """Reverses the type swap. Lossy: hr_director/admin were merged into
    hr_admin in upgrade(), so which of the two a row originally was is no
    longer recoverable — every hr_admin row downgrades to hr_director."""
    op.execute("ALTER TYPE user_role RENAME TO user_role_new")
    op.execute(
        "CREATE TYPE user_role AS ENUM ('applicant', 'hr_director', 'evaluator', 'admin')"
    )
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN role TYPE user_role
        USING (
            CASE role::text
                WHEN 'hr_admin' THEN 'hr_director'
                ELSE role::text
            END
        )::user_role
        """
    )
    op.execute("DROP TYPE user_role_new")
