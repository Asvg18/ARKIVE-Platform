"""The Skill Matching Agent's retrieval pipeline (hybrid RAG) as a
LangGraph StateGraph (run_rag_analysis); its verdicts are settled in
verdict_settlement.
"""

from __future__ import annotations

import logging
import operator
from typing import Annotated, Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.domain import rag_dfa
from app.schemas.skill_match import AuditVerdict, RAGTrace, RequirementCheck, SkillMatchAnalysis
from app.services.agents.base import SubAgent
from app.services.agents.rag_catalog import (
    AUDIT,
    CLARIFY,
    COMPLIANCE,
    CONTEXT_ROUTING,
    INGESTION,
    SCORING,
    VALIDATION,
    _claim_key,
)
# the verdict checks; the private names are re-exported for the tests
from app.services.verdict_settlement import (  # noqa: F401
    _degree_finding,
    _named_fields,
    _normalized,
    _quote_holds,
    _settle_verdicts,
    _verified_checks,
)

__all__ = ["RAG_GRAPH", "RAGState", "run_rag_analysis"]

_log = logging.getLogger(__name__)


class RAGState(TypedDict, total=False):
    """The automaton's state: the only thing the transition functions
    read. Plain, serializable values. `path` accumulates (`operator.add`),
    so a repeated "scoring" in it shows a clarify retry."""

    # seeded by the caller
    combined_score: float

    # ingestion
    resume_chunks: list[str]
    # each chunk's resume section ("education", ...), aligned with
    # resume_chunks; see skill_matching._ensure_section_evidence
    chunk_sections: list[str]
    structured_chunk_count: int

    # validation -- the symbol after_validation branches on
    has_usable_evidence: bool

    # compliance
    redacted_chunks: list[str]
    redactions: int

    # context_routing
    requirements: list[str]
    # False when the job had no parsed requirement lines (one-blob
    # fallback); retrying cannot find better evidence, so no clarify cycle
    jd_has_requirements: bool
    evidence: list[dict]
    # carried so a clarify retry re-ranks instead of paying to re-embed
    chunk_embeddings: list[list[float]]
    # whether LLM-written probes were actually used; the expansion call
    # can fail and fall back even when settings.rag_query_expansion is on
    expanded_queries: bool

    # scoring / audit -- dumps, not model instances, so state stays plain
    analysis: dict
    verdict: dict
    unsupported_claims: list[str]

    # clarify -- the budget after_clarify reads
    clarify_loops: int

    # set only by the two dead-end nodes
    terminal_state: str
    degraded_reason: str

    path: Annotated[list[str], operator.add]


def _node(agent: SubAgent):
    """Adapts a SubAgent to LangGraph's node signature, unwrapping
    `configurable` (as in orchestration.py)."""

    def node(state: RAGState, config: RunnableConfig) -> dict[str, Any]:
        return agent.run(state, config["configurable"])

    node.__name__ = f"{agent.name}_node"
    return node


_UNREADABLE_SUMMARY = (
    "This resume could not be read into any assessable detail, so no evidence "
    "was available to screen against the job's requirements, and the fit score "
    "above has no requirement check behind it. This application needs a "
    "human review of the original file. Treat the absence of an assessment as "
    "a problem with the document, not as a finding about the candidate."
)


_UNVERIFIED_PREFIX = (
    "[Unverified by the Critic Agent: read against the resume before relying "
    "on it.] "
)


def _rejected_node(state: RAGState, config: RunnableConfig) -> dict[str, Any]:
    return {
        "terminal_state": "rejected",
        "degraded_reason": "No usable evidence could be extracted from the resume.",
        "path": ["rejected"],
    }


def _manual_review_node(state: RAGState, config: RunnableConfig) -> dict[str, Any]:
    """Reached when the Critic still objects after the retry budget, or
    when retrying cannot help (no parsed requirements). Keeps the last
    draft, minus the claims the Critic named as unsupported."""
    if state.get("jd_has_requirements", True):
        reason = (
            f"The Critic Agent could not verify this assessment after "
            f"{rag_dfa.MAX_CLARIFY_LOOPS} clarification attempts; unsupported "
            "claims were removed and the remainder is unverified."
        )
    else:
        reason = (
            "This job posting has no qualifications or requirements filled in, so "
            "there was nothing specific to screen the resume against and the "
            "assessment could not be verified. Add them in the Job Opening Builder "
            "and re-run screening."
        )
    return {
        "terminal_state": "manual_review",
        "degraded_reason": reason,
        "path": ["manual_review"],
    }


def _after_validation(state: RAGState) -> str:
    return rag_dfa.after_validation(has_usable_evidence=state["has_usable_evidence"])


def _after_audit(state: RAGState) -> str:
    return rag_dfa.after_audit(
        is_grounded=AuditVerdict(**state["verdict"]).is_grounded,
        # always set by the Context Router before audit; True if not, so
        # retries are never silently suppressed
        can_retry=state.get("jd_has_requirements", True),
    )


def _after_clarify(state: RAGState) -> str:
    return rag_dfa.after_clarify(clarify_loops=state.get("clarify_loops", 0))


def _targets(source: str) -> list[str]:
    """path_map for a conditional edge, taken from the automaton rather
    than written out again beside it."""
    return sorted(rag_dfa.TRANSITIONS[source])


def _build_graph():
    """Wires the seven agents and the two dead ends to rag_dfa's table.

    Each conditional edge calls a rag_dfa transition function with values
    lifted out of state, and each path_map is read off TRANSITIONS, so an
    undeclared edge fails to build. The clarify cycle is bounded by
    `clarify_loops`, incremented by the Clarify Agent and read by
    rag_dfa.after_clarify. Session/ORM objects travel through
    RunnableConfig (`configurable`), never through serializable state.
    """
    graph = StateGraph(RAGState)

    graph.add_node("ingestion", _node(INGESTION))
    graph.add_node("validation", _node(VALIDATION))
    graph.add_node("compliance", _node(COMPLIANCE))
    graph.add_node("context_routing", _node(CONTEXT_ROUTING))
    graph.add_node("scoring", _node(SCORING))
    graph.add_node("audit", _node(AUDIT))
    graph.add_node("clarify", _node(CLARIFY))
    graph.add_node("rejected", _rejected_node)
    graph.add_node("manual_review", _manual_review_node)

    graph.add_edge(START, rag_dfa.START_STATE)

    # unconditional edges -- states the table gives exactly one successor
    graph.add_edge("ingestion", "validation")
    graph.add_edge("compliance", "context_routing")
    graph.add_edge("context_routing", "scoring")
    graph.add_edge("scoring", "audit")
    graph.add_edge("rejected", END)
    graph.add_edge("manual_review", END)

    # the branching states -- δ, one function each
    graph.add_conditional_edges("validation", _after_validation, _targets("validation"))
    graph.add_conditional_edges("audit", _after_audit, _targets("audit"))
    graph.add_conditional_edges("clarify", _after_clarify, _targets("clarify"))

    return graph.compile()


# compiled once at import: pure structure; model clients arrive per call
# through `configurable`
RAG_GRAPH = _build_graph()


def _answered_gaps(state: RAGState, checks: list[RequirementCheck]) -> set[str]:
    """Gaps written about a requirement whose settled verdict is a verified
    `met` -- a gap the verdicts, after the quote check and the re-check,
    say is not one.

    Which requirement a gap is about is the Critic's ruling on it
    (AuditVerdict.claim_reviews), not a guess from its wording. Without
    rulings nothing is dropped. Without this, a gap the re-check overturned
    would stand beside the verdict contradicting it."""
    met = {check.requirement for check in checks if check.verdict == "met" and check.verified}
    reviews = (state.get("verdict") or {}).get("claim_reviews", [])
    return {
        _claim_key(review["claim"])
        for review in reviews
        if review.get("requirement", "").strip() in met
    }


def _analysis_for(state: RAGState, checks: list[RequirementCheck]) -> SkillMatchAnalysis:
    """The assessment to return, given where the automaton stopped."""
    terminal = state.get("terminal_state", "")

    if terminal == "rejected":
        return SkillMatchAnalysis(
            strengths=[],
            gaps=["The resume could not be read into any assessable detail."],
            summary=_UNREADABLE_SUMMARY,
        )

    analysis = SkillMatchAnalysis(**state["analysis"])
    answered = _answered_gaps(state, checks)
    gaps = [g for g in analysis.gaps if _claim_key(g) not in answered]
    if terminal != "manual_review":
        return analysis.model_copy(update={"gaps": gaps, "requirement_checks": checks})

    rejected = {claim.strip() for claim in state.get("unsupported_claims", [])}
    return SkillMatchAnalysis(
        strengths=[s for s in analysis.strengths if s.strip() not in rejected],
        gaps=[g for g in gaps if g.strip() not in rejected],
        summary=_UNVERIFIED_PREFIX + analysis.summary,
        # audited on their own (_settle_verdicts), so they still count
        # even though the prose above did not pass the Critic
        requirement_checks=checks,
    )


def run_rag_analysis(
    *,
    llm,
    embeddings,
    resume,
    requisition,
    combined_score: float,
    requirement_signals: dict[str, float] | None = None,
) -> tuple[SkillMatchAnalysis, RAGTrace]:
    """Run the retrieval automaton for one application.

    Returns the assessment and the path taken to reach it. Any model
    failure raises AIExtractionFailedError, which the router maps to 502.

    `combined_score` is the arithmetic half, computed outside this graph
    and kept in state for the record only: no agent here is shown it, so
    none can be anchored by it or change it.

    What this graph contributes to the score is the requirement checks on
    the returned analysis -- one per requirement, settled by
    _settle_verdicts -- which run_skill_matching turns into the coverage
    half. They are settled and counted whether or not the Critic signed
    off the written assessment; only `rejected` (nothing to retrieve
    over) returns none, and the score is then the arithmetic half alone.
    A `terminal_state` in rag_dfa.TERMINAL means the written assessment
    is shown to HR as unverified; it does not flag the application.
    """
    ctx = {"llm": llm, "embeddings": embeddings, "resume": resume, "requisition": requisition}
    final: RAGState = RAG_GRAPH.invoke(
        {"combined_score": combined_score, "clarify_loops": 0, "path": []},
        config={"configurable": ctx},
    )

    # no dead end reached -> the Critic signed off, which is the one
    # accepting state
    terminal = final.get("terminal_state") or "audit"
    checks, objections, rechecked = (
        ([], 0, 0) if terminal == "rejected" else _settle_verdicts(final, ctx, requirement_signals or {})
    )
    trace = RAGTrace(
        path=final.get("path", []),
        terminal_state=terminal,
        clarify_loops=final.get("clarify_loops", 0),
        redactions=final.get("redactions", 0),
        requirements_retrieved=len(final.get("requirements", [])),
        expanded_queries=final.get("expanded_queries", False),
        degraded_reason=final.get("degraded_reason", ""),
        verdict_objections=objections,
        verdicts_rechecked=rechecked,
    )
    if terminal != "audit":
        _log.warning(
            "RAG pipeline for requisition %s stopped in %r: %s",
            getattr(requisition, "id", "?"),
            terminal,
            trace.degraded_reason,
        )
    return _analysis_for(final, checks), trace
