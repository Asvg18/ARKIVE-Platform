"""The agent hierarchy's guarantees.

These cover what the `Agent` base class was introduced to make
impossible, rather than re-testing each agent's own logic (its own test
file already does that). The bug this replaced was silent: an agent's
name lived in its own module and *again* in a registry in
services/synthesis.py, so a rename could leave the Synthesis tab
showing a stale label -- or an agent could log under a name nothing
displayed at all.
"""

from __future__ import annotations

import pytest

from app.models.agent_run import AgentRun
from app.services.agents import AGENTS, BY_NAME, Agent, PipelineAgent
from app.services.agents.catalog import DECISION_SUPPORT, SKILL_MATCHING


def test_every_agent_is_uniquely_named() -> None:
    names = [a.name for a in AGENTS]
    assert len(names) == len(set(names)) == len(BY_NAME)


def test_every_agent_declares_its_identity() -> None:
    """`__init_subclass__` enforces this at import time; this asserts the
    enforcement is actually reaching every catalogued agent."""
    for agent in AGENTS:
        assert agent.name and agent.label and agent.duty
        assert agent.kind in ("event", "derived")


def test_a_subclass_cannot_omit_its_identity() -> None:
    with pytest.raises(TypeError, match="must declare a non-empty `label`"):

        class Nameless(Agent):
            name = "nameless_agent"
            duty = "Does something."


def test_a_subclass_cannot_reuse_an_existing_agent_name() -> None:
    """Names are written into AgentRun rows, so a duplicate would silently
    merge two agents' execution histories."""
    with pytest.raises(TypeError, match="reuses agent name"):

        class Impostor(Agent):
            name = "matching_agent"
            label = "Impostor"
            duty = "Pretends to be the Skill Matching Agent."


def test_only_the_pre_screening_graph_agents_are_runnable() -> None:
    """Exactly two agents are LangGraph nodes. The other six run
    elsewhere -- Exam Scheduling when an applicant books an exam session
    -- or, in Decision Support's case, never run at all."""
    runnable = {a.name for a in AGENTS if isinstance(a, PipelineAgent)}
    assert runnable == {"matching_agent", "interview_analysis_agent"}


def test_the_derived_agent_refuses_to_write_a_run_row(db_session) -> None:
    """Decision Support is computed from the other agents' outputs. If it
    ever logged a run, the Synthesis tab would report it as having executed
    and the final score would look like an agent's opinion rather than a
    weighted sum of recorded facts."""
    assert DECISION_SUPPORT.kind == "derived"
    with pytest.raises(TypeError, match="derived agent"):
        DECISION_SUPPORT.log(
            db_session, application_id=1, triggered_by_stage="final_decision", output={}
        )


def test_log_writes_the_agents_own_name(db_session, make_job, make_application) -> None:
    """The reason `log` lives on the base class: an agent can no longer be
    logged under a name that is not its own."""
    application = make_application(make_job(["document_upload", "skill_matching"]))
    SKILL_MATCHING.log(
        db_session,
        application_id=application.id,
        triggered_by_stage="skill_matching",
        output={"probe": True},
    )
    db_session.flush()
    row = (
        db_session.query(AgentRun)
        .filter(AgentRun.application_id == application.id)
        .order_by(AgentRun.id.desc())
        .first()
    )
    assert row.agent_name == SKILL_MATCHING.name == "matching_agent"
    assert row.output == {"probe": True}
