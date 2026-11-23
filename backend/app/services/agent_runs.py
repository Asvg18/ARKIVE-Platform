"""Tiny shared writer for the AgentRun log (see app/models/agent_run.py)
-- keeps every agent logging through one path instead of each one
rolling its own insert."""

from sqlalchemy.orm import Session

from app.models.agent_run import AgentRun


def log_agent_run(
    db: Session, *, application_id: int, agent_name: str, triggered_by_stage: str, output: dict
) -> None:
    db.add(
        AgentRun(
            application_id=application_id,
            agent_name=agent_name,
            triggered_by_stage=triggered_by_stage,
            output=output,
        )
    )
