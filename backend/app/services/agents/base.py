"""The single declaration of each agent's identity, so the name in the
AgentRun log and the label/duty shown in the UI can't drift apart.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from sqlalchemy.orm import Session

from app.services.agent_runs import log_agent_run

AgentKind = Literal["event", "derived"]

# names seen so far -- catches a copy-pasted subclass that forgot to
# change `name`, so it fails at import instead of silently logging into
# another agent's rows
_TAKEN: dict[str, type["Agent"]] = {}


class Agent(ABC):
    """One named participant in the hiring pipeline's execution log
    (Decision Support is `derived` and never runs).

    Identity (`name`, `label`, `duty`, `kind`) is ClassVar: it belongs to
    the class, not a run, and `__init_subclass__` refuses at import a
    subclass that skips a field or reuses a name. The singletons in
    catalog.py are the instances the app uses.
    """

    #: written straight to AgentRun.agent_name -- it's in the DB, so
    #: renaming this is a migration, not a refactor
    name: ClassVar[str]
    #: shown in the Synthesis tab's agent trail
    label: ClassVar[str]
    #: one-liner shown as the agent's subtitle in the coverage list
    duty: ClassVar[str]
    #: "derived" = computed from other agents' outputs, never writes its own AgentRun row
    kind: ClassVar[AgentKind] = "event"

    #: marks a class that exists only to be subclassed, not used directly
    abstract: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__dict__.get("abstract", False):
            return
        for field in ("name", "label", "duty"):
            if not getattr(cls, field, None):
                raise TypeError(f"{cls.__name__} must declare a non-empty `{field}`")
        clash = _TAKEN.get(cls.name)
        if clash is not None:
            raise TypeError(
                f"{cls.__name__} reuses agent name {cls.name!r}, already taken by "
                f"{clash.__name__}. Agent names are written to AgentRun rows and "
                "must be unique."
            )
        _TAKEN[cls.name] = cls

    def log(
        self,
        db: Session,
        *,
        application_id: int,
        triggered_by_stage: str,
        output: dict,
    ) -> None:
        """The only place `agent_name` gets supplied, so an agent can't
        log itself under the wrong name. Doesn't commit -- caller owns
        the transaction, same as when each agent called log_agent_run
        directly."""
        if self.kind == "derived":
            raise TypeError(
                f"{type(self).__name__} is a derived agent: it is computed from other "
                "agents' outputs and must not write an AgentRun row."
            )
        log_agent_run(
            db,
            application_id=application_id,
            agent_name=self.name,
            triggered_by_stage=triggered_by_stage,
            output=output,
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} {self.name!r}>"


class PipelineAgent(Agent):
    """A node of the AI Pre-Screening `StateGraph`. orchestration.py passes
    the config's `configurable` mapping as `ctx`. Returns a plain dict,
    which is merged into graph state.
    """

    abstract = True

    @abstractmethod
    def run(self, state: Mapping[str, Any], ctx: Mapping[str, Any]) -> dict[str, Any]:
        pass


# Same guard as _TAKEN, kept separate: a sub-agent's name is a graph node
# id and a trace entry, never an AgentRun.agent_name, so the two
# namespaces are allowed to be independent and collisions across them
# wouldn't mean anything.
_SUB_TAKEN: dict[str, type["SubAgent"]] = {}


class SubAgent(ABC):
    """A named agent *inside* another agent's sub-graph.

    The seven that make up the hybrid-RAG retrieval pipeline
    (services/rag_pipeline.py) are these: they run as nodes of the
    Skill Matching Agent's own StateGraph, not of the pre-screening one.

    Not `Agent`s: they have no AgentRun row or coverage entry. The log
    records the pipeline as a whole under `matching_agent`; which
    sub-agents ran is kept in SkillMatchResult.rag_trace.

    Identity is still checked at import, so a copied node that forgot to
    change `name` cannot overwrite a sibling in the node table.
    """

    abstract: ClassVar[bool] = False

    #: graph node id -- must equal a state in domain/rag_dfa.TRANSITIONS
    name: ClassVar[str]
    #: shown when a trace is rendered for HR
    label: ClassVar[str]
    #: one-liner describing this agent's single responsibility
    duty: ClassVar[str]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__dict__.get("abstract", False):
            return
        for field in ("name", "label", "duty"):
            if not getattr(cls, field, None):
                raise TypeError(f"{cls.__name__} must declare a non-empty `{field}`")
        clash = _SUB_TAKEN.get(cls.name)
        if clash is not None:
            raise TypeError(
                f"{cls.__name__} reuses sub-agent name {cls.name!r}, already taken by "
                f"{clash.__name__}. Sub-agent names are graph node ids and must be unique."
            )
        _SUB_TAKEN[cls.name] = cls

    @abstractmethod
    def run(self, state: Mapping[str, Any], ctx: Mapping[str, Any]) -> dict[str, Any]:
        """Same `(state, ctx) -> dict` contract as PipelineAgent, for the
        same reason: the returned dict is merged into graph state."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} {self.name!r}>"
