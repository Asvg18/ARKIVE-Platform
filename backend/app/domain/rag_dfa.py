"""The retrieval pipeline's DFA (which agent runs next inside one skill
match), held as data; not the hiring-stage DFA in dfa.py. Diagram:
docs/ARKIVE-skill-matching-algorithm.md, section 3.
"""

from __future__ import annotations

from typing import Literal

__all__ = [
    "ACCEPTING",
    "END",
    "MAX_CLARIFY_LOOPS",
    "START_STATE",
    "TERMINAL",
    "TRANSITIONS",
    "RAGStateName",
    "after_audit",
    "after_clarify",
    "after_validation",
    "is_declared_transition",
    "unreachable_states",
]

#: LangGraph's terminal sentinel as a plain string, so this pure module
#: imports no graph runtime; test_rag_dfa.py asserts it equals END.
END = "__end__"

RAGStateName = Literal[
    "ingestion",
    "validation",
    "compliance",
    "context_routing",
    "scoring",
    "audit",
    "clarify",
    "rejected",
    "manual_review",
]

START_STATE: RAGStateName = "ingestion"

#: Rewrites the Clarify Agent may ask for before routing to manual
#: review. This bound is what makes the cycle halt (the Critic is an LLM
#: and could object forever). Counted in *rewrites*, while
#: RAGState.clarify_loops counts *visits*: visit N+1 routes to
#: manual_review (see after_clarify's `>`).
MAX_CLARIFY_LOOPS = 2

#: The transition function δ, as a table: states are graph nodes. Every
#: edge the compiled StateGraph may have appears here and nowhere else;
#: test_rag_dfa.py asserts the compiled graph's edges equal it. It has one
#: cycle, audit -> clarify -> scoring -> audit, bounded by
#: MAX_CLARIFY_LOOPS.
TRANSITIONS: dict[str, frozenset[str]] = {
    "ingestion": frozenset({"validation"}),
    "validation": frozenset({"compliance", "rejected"}),
    "compliance": frozenset({"context_routing"}),
    "context_routing": frozenset({"scoring"}),
    "scoring": frozenset({"audit"}),
    # manual_review straight from audit is the "retrying cannot help"
    # exit -- see after_audit. Not the same as clarify's budget-spent
    # exit, which is reached only after actually trying.
    "audit": frozenset({"clarify", "manual_review", END}),
    "clarify": frozenset({"scoring", "manual_review"}),
    # Both dead ends still have to reach END -- LangGraph has no notion
    # of a node that simply stops, and "halts without an accepting
    # transition" isn't a DFA either.
    "rejected": frozenset({END}),
    "manual_review": frozenset({END}),
}

#: States whose only transition is END: the pipeline stopped early and
#: HR sees a degraded analysis. Never an auto-rejection of the candidate.
TERMINAL: frozenset[str] = frozenset({"rejected", "manual_review"})

#: The one path that produced a fully audited analysis. Named separately
#: from TERMINAL because "stopped" and "succeeded" are different claims,
#: and the trace persisted for HR reports which one happened.
ACCEPTING: frozenset[str] = frozenset({"audit"})


# ---------------------------------------------------------------------------
# δ — the transition function, one per branching state; each is a
# LangGraph conditional edge. They take primitives, never the state dict
# or ORM objects, so this stays pure and every input can be enumerated.
# ---------------------------------------------------------------------------


def after_validation(*, has_usable_evidence: bool) -> RAGStateName:
    """An empty corpus stops here: there would be no evidence to judge
    against."""
    return "compliance" if has_usable_evidence else "rejected"


def after_audit(*, is_grounded: bool, can_retry: bool = True) -> str:
    """The Critic's verdict is the input symbol. `is_grounded` means every
    claim in the analysis traces to a retrieved evidence chunk -- the
    accepting transition.

    `can_retry` is False when retrying cannot help (no parsed requirement
    lines, so one block of prose is the only query); that run goes
    straight to manual review. The loop budget is read only in
    after_clarify."""
    if is_grounded:
        return END
    return "clarify" if can_retry else "manual_review"


def after_clarify(*, clarify_loops: int) -> RAGStateName:
    """`clarify_loops` is the number of times the Clarify Agent has now
    run, incremented by that node before this is called.

    `>` rather than `>=`: the first MAX_CLARIFY_LOOPS visits each buy a
    rewrite (with `>=`, 2 would buy only one). The clarify node also calls
    this, to skip retrieval on the terminating visit."""
    return "manual_review" if clarify_loops > MAX_CLARIFY_LOOPS else "scoring"


# ---------------------------------------------------------------------------
# Table queries. Used by the tests that hold the graph to this spec.
# ---------------------------------------------------------------------------


def is_declared_transition(source: str, target: str) -> bool:
    """Whether source -> target is an edge of this automaton."""
    return target in TRANSITIONS.get(source, frozenset())


def unreachable_states() -> frozenset[str]:
    """States no transition leads to, ignoring the start state. Non-empty
    is always a bug in the table."""
    reached = {target for targets in TRANSITIONS.values() for target in targets}
    return frozenset(TRANSITIONS.keys() - reached - {START_STATE})
