"""The AI Pre-Screening agents as a LangGraph StateGraph.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.schemas.applicant import PreScreeningAnswer
from app.schemas.interview_analysis import InterviewAnalysisResult
from app.schemas.skill_match import SkillMatchResult
from app.services.agents import INTERVIEW_ANALYSIS, SKILL_MATCHING, PipelineAgent

__all__ = ["PRE_SCREENING_GRAPH", "PreScreeningState", "run_pre_screening_pipeline"]


class PreScreeningState(TypedDict, total=False):
    """Plain, serializable data only. `has_questions` is copied out of the
    requisition so the edges can branch on state alone."""

    application_id: int
    has_questions: bool

    match: SkillMatchResult | None
    analysis: InterviewAnalysisResult | None


def _node(agent: PipelineAgent):
    """Adapts a PipelineAgent to LangGraph's node signature, unwrapping
    `configurable` so the agent stays callable with a plain dict too."""

    def node(state: PreScreeningState, config: RunnableConfig) -> dict[str, Any]:
        return agent.run(state, config["configurable"])

    node.__name__ = f"{agent.name}_node"
    return node


def _after_skill_matching(state: PreScreeningState) -> Literal["interview_analysis", "__end__"]:
    """Skips interview_analysis entirely when there's nothing for it to
    do -- no questions to read."""
    return "interview_analysis" if state["has_questions"] else END


def _entry(
    state: PreScreeningState,
) -> Literal["skill_matching", "interview_analysis", "__end__"]:
    """Skip skill matching when a match was stored at resume upload. Without
    one (scoring failed at upload, or an older application) the node runs,
    since the flag decision needs a match."""
    if state.get("match") is None:
        return "skill_matching"
    return _after_skill_matching(state)


def _build_graph():
    """START -> skill_matching (only when no match was stored, see _entry)
    -> interview_analysis (only when the job has questions) -> END.
    PRE_SCREENING_GRAPH.get_graph().draw_mermaid() draws it."""
    graph = StateGraph(PreScreeningState)
    graph.add_node("skill_matching", _node(SKILL_MATCHING))
    graph.add_node("interview_analysis", _node(INTERVIEW_ANALYSIS))

    graph.add_conditional_edges(START, _entry)
    graph.add_conditional_edges("skill_matching", _after_skill_matching)
    graph.add_edge("interview_analysis", END)
    return graph.compile()


# compiled once at import: pure structure, no I/O or model clients
PRE_SCREENING_GRAPH = _build_graph()


def run_pre_screening_pipeline(
    db,
    *,
    application_id: int,
    requisition,
    resume,
    answers: list[PreScreeningAnswer],
    match: SkillMatchResult | None = None,
) -> PreScreeningState:
    """Run the graph for one application. Database writes stay with the
    router, and Session/ORM objects travel through RunnableConfig, never
    through (serializable) state. Agent exceptions
    (ExtractionNotConfiguredError / AIExtractionFailedError) propagate
    unchanged for the router to map to 503/502.

    `match` is the result stored at resume upload; passing it skips the
    skill_matching node (see _entry)."""
    return PRE_SCREENING_GRAPH.invoke(
        {
            "application_id": application_id,
            "has_questions": bool(requisition.pre_screening_questions),
            "match": match,
        },
        config={
            "configurable": {
                "db": db,
                "requisition": requisition,
                "resume": resume,
                "answers": answers,
            }
        },
    )
