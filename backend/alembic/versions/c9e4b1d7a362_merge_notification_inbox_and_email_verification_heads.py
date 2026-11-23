"""merge notification inbox and email verification heads

The notifications inbox (a7c3e9f15d28) and applicant email verification
(fa31c8e4b927) were each added on top of f4d9a2c6b815 at the same time.
Joins the two so `alembic upgrade head` has one head again. Changes
nothing itself.
"""

from typing import Sequence, Union


revision: str = "c9e4b1d7a362"
down_revision: Union[str, Sequence[str], None] = ("a7c3e9f15d28", "fa31c8e4b927")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
