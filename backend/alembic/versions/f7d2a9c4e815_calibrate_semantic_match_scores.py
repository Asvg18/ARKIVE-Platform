"""calibrate semantic match scores

Revision ID: f7d2a9c4e815
Revises: e3b7c9d2a145
Create Date: 2026-09-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7d2a9c4e815'
down_revision: Union[str, Sequence[str], None] = 'e3b7c9d2a145'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copies of services/skill_matching.py and domain/insights.py as
# of this revision -- deliberately not imported. A migration has to keep
# doing what it did the day it was written, even after someone retunes
# the live constants.
_COSINE_FLOOR = 0.20
_COSINE_CEILING = 0.70
_SEMANTIC_WEIGHT = 0.6
_FLAG_THRESHOLD = 60.0
_UNVERIFIED_TERMINAL_STATES = {"rejected", "manual_review"}

_stage_instances = sa.table(
    'stage_instances',
    sa.column('id', sa.Integer),
    sa.column('payload', sa.JSON),
)


def _calibrated(cosine: float) -> float:
    span = _COSINE_CEILING - _COSINE_FLOOR
    return round(max(0.0, min(100.0, (cosine - _COSINE_FLOOR) / span * 100)), 1)


def _combined(semantic: float, keyword: float) -> float:
    return round(_SEMANTIC_WEIGHT * semantic + (1 - _SEMANTIC_WEIGHT) * keyword, 1)


def _rescale(match: dict, combined_key: str) -> dict:
    # before this revision semantic_score *was* the cosine, times 100
    cosine = match["semantic_score"] / 100
    semantic = _calibrated(cosine)
    return {
        **match,
        "cosine_similarity": round(cosine, 4),
        "semantic_score": semantic,
        combined_key: _combined(semantic, match["keyword_score"]),
    }


def _unscale(match: dict, combined_key: str) -> dict:
    semantic = round(match["cosine_similarity"] * 100, 1)
    restored = {**match, "semantic_score": semantic, combined_key: _combined(semantic, match["keyword_score"])}
    del restored["cosine_similarity"]
    return restored


def _refresh_pending_flag(payload: dict) -> None:
    """Re-decides the flag on a payload nothing has acted on yet.

    Only called for a payload without the applicant's pre-screening
    answers, i.e. one stored at résumé upload. submit_pre_screening reads
    `flagged` straight out of it, so it has to follow the new score.
    Once pre-screening has been submitted, the flag already decided what
    happened to the application, and HR may have resolved it since --
    that is history, and it stays as it was."""
    below = payload["match_score"] < _FLAG_THRESHOLD
    trace = payload.get("rag_trace") or {}
    unverified = trace.get("terminal_state") in _UNVERIFIED_TERMINAL_STATES
    payload["flagged"] = below or unverified
    payload["flag_reason"] = "below_threshold" if below else "unverified_assessment" if unverified else ""
    # other openings are only ever suggested to a below-threshold
    # candidate, and only ones that clear the threshold themselves
    payload["suggested_requisitions"] = [
        s for s in payload.get("suggested_requisitions") or [] if below and s["combined_score"] >= _FLAG_THRESHOLD
    ]


def _skill_matching_rows(conn) -> list:
    return conn.execute(
        sa.select(_stage_instances.c.id, _stage_instances.c.payload).where(
            sa.text("stage_type = 'skill_matching'")
        )
    ).all()


def _save(conn, row_id: int, payload: dict) -> None:
    conn.execute(
        sa.update(_stage_instances).where(_stage_instances.c.id == row_id).values(payload=payload)
    )


def upgrade() -> None:
    """Moves every stored skill-match score onto the calibrated semantic
    scale.

    semantic_score used to be raw cosine similarity x 100, which a
    résumé and a job posting never get near -- so every combined score
    topped out in the high 70s, and the 80+ "strong match" band was
    unreachable. New scores map cosine 0.20-0.70 onto 0-100 instead (see
    _semantic_score in services/skill_matching.py). Converted here so a
    ranking or percentile never mixes the two scales.

    No embeddings call and no BM25 rerun: the old semantic_score is the
    cosine, so the new one follows from it, and keyword_score is
    unchanged. The raw cosine is kept as `cosine_similarity`, which also
    marks a row as done -- running this twice changes nothing.

    Not touched: an applied flag decision (see _refresh_pending_flag),
    the AgentRun log (an audit trail of what the agent said at the time),
    and prose the analysis agents wrote with the old number in front of
    them."""
    conn = op.get_bind()
    for row_id, payload in _skill_matching_rows(conn):
        if (
            not payload
            or "semantic_score" not in payload
            or "keyword_score" not in payload
            or payload.get("cosine_similarity") is not None
        ):
            continue
        updated = _rescale(payload, "match_score")
        updated["suggested_requisitions"] = [
            _rescale(s, "combined_score") if s.get("cosine_similarity") is None else s
            for s in payload.get("suggested_requisitions") or []
        ]
        if "answers" not in updated:
            _refresh_pending_flag(updated)
        _save(conn, row_id, updated)


def downgrade() -> None:
    """Back to raw cosine x 100, for every calibrated row -- including
    ones scored after the upgrade, which the downgraded code would
    otherwise misread. Two things may not come back exactly: a combined
    score can differ from the original by 0.1 (it was first rounded from
    unrounded parts), and a suggestion the upgrade dropped from a pending
    payload stays dropped."""
    conn = op.get_bind()
    for row_id, payload in _skill_matching_rows(conn):
        if not payload or payload.get("cosine_similarity") is None:
            continue
        restored = _unscale(payload, "match_score")
        restored["suggested_requisitions"] = [
            _unscale(s, "combined_score") if s.get("cosine_similarity") is not None else s
            for s in payload.get("suggested_requisitions") or []
        ]
        if "answers" not in restored:
            _refresh_pending_flag(restored)
        _save(conn, row_id, restored)
