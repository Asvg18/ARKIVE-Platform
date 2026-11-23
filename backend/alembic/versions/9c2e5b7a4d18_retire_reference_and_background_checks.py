"""retire reference and background checks

Revision ID: 9c2e5b7a4d18
Revises: e6a3c9f1d7b2
Create Date: 2026-09-30 00:00:00.000000

"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9c2e5b7a4d18'
down_revision: Union[str, Sequence[str], None] = 'e6a3c9f1d7b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RETIRED = ('reference_check', 'background_check')

_requisitions = sa.table(
    'job_requisitions',
    sa.column('id', sa.Integer),
    sa.column('workflow_definition', sa.JSON),
)
_applications = sa.table(
    'candidate_applications',
    sa.column('id', sa.Integer),
    sa.column('requisition_id', sa.Integer),
    sa.column('current_stage', sa.String),
)
_instances = sa.table(
    'stage_instances',
    sa.column('id', sa.Integer),
    sa.column('application_id', sa.Integer),
    sa.column('stage_type', sa.String),
    sa.column('status', sa.String),
)
_history = sa.table(
    'stage_history',
    sa.column('application_id', sa.Integer),
    sa.column('from_stage', sa.String),
    sa.column('to_stage', sa.String),
    sa.column('triggered_by', sa.String),
    sa.column('timestamp', sa.DateTime(timezone=True)),
)


# the columns are Postgres enums; a bare string parameter would be sent
# as varchar and refused
_STAGE_TYPE = postgresql.ENUM(name='stage_type', create_type=False)
_STAGE_STATUS = postgresql.ENUM(name='stage_status', create_type=False)


def _stage(value: str):
    return sa.cast(value, _STAGE_TYPE)


def upgrade() -> None:
    """Reference and background checks are no longer part of ARKIVE.

    Takes both stages out of every job's workflow, so the DFA, the stage
    counts and the hire gate stop expecting them. Anyone sitting on one
    moves to the next stage that survives, with the move written to
    stage_history like any other. Their stage_instances rows go too --
    nothing reads a stage the workflow no longer names except the
    applicant's own stage list, which would otherwise keep showing it.

    The enum values stay: stage_history keeps its record of candidates
    who passed through these stages before today."""
    conn = op.get_bind()
    now = datetime.now(timezone.utc)

    for req_id, workflow in conn.execute(sa.select(_requisitions.c.id, _requisitions.c.workflow_definition)):
        if not workflow or not any(stage in _RETIRED for stage in workflow):
            continue
        kept = [stage for stage in workflow if stage not in _RETIRED]

        parked = conn.execute(
            sa.select(_applications.c.id, _applications.c.current_stage).where(
                _applications.c.requisition_id == req_id,
                _applications.c.current_stage.in_([_stage(s) for s in _RETIRED]),
            )
        ).all()
        for app_id, current in parked:
            after = workflow[workflow.index(current) + 1 :]
            target = next((s for s in after if s not in _RETIRED), kept[-1])
            conn.execute(
                _applications.update()
                .where(_applications.c.id == app_id)
                .values(current_stage=_stage(target))
            )
            updated = conn.execute(
                _instances.update()
                .where(_instances.c.application_id == app_id, _instances.c.stage_type == _stage(target))
                .values(status=sa.cast('in_progress', _STAGE_STATUS))
            )
            if updated.rowcount == 0:
                conn.execute(
                    _instances.insert().values(
                        application_id=app_id,
                        stage_type=_stage(target),
                        status=sa.cast('in_progress', _STAGE_STATUS),
                    )
                )
            conn.execute(
                _history.insert().values(
                    application_id=app_id,
                    from_stage=_stage(current),
                    to_stage=_stage(target),
                    triggered_by='system',
                    timestamp=now,
                )
            )

        conn.execute(
            _requisitions.update().where(_requisitions.c.id == req_id).values(workflow_definition=kept)
        )

    conn.execute(_instances.delete().where(_instances.c.stage_type.in_([_stage(s) for s in _RETIRED])))


def downgrade() -> None:
    """One-way. Where each check sat in each workflow, and any result
    HR had recorded on one, are gone -- putting the stages back at a
    guessed position would invent a pipeline no job ever had."""
    pass
