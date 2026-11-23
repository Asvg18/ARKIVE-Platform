"""Tests for the Pre-Screening LangGraph StateGraph -- services/
orchestration.py.

Two things pinned here. First, that the graph really is a graph: it
declares the agent nodes and the conditional branches, so "we use
LangGraph" is a checkable claim, not just a line in the title. Second,
that its skip conditions route exactly as plain `if`s over the same
state would. Exam booking is not a node: it belongs to the Examination
stage.

The routing functions are pure and take only state, so they're tested
directly rather than through more end-to-end runs of the real agents.
"""

from langgraph.graph import END

from app.services.orchestration import PRE_SCREENING_GRAPH, _after_skill_matching, _entry


def test_graph_declares_the_two_agent_nodes():
    nodes = set(PRE_SCREENING_GRAPH.get_graph().nodes)
    assert {"skill_matching", "interview_analysis"} <= nodes
    assert "exam_scheduling" not in nodes


def test_graph_entry_point_is_skill_matching():
    edges = PRE_SCREENING_GRAPH.get_graph().edges
    assert any(e.source == "__start__" and e.target == "skill_matching" for e in edges)


def test_graph_has_a_conditional_branch_out_of_skill_matching():
    """A straight line would have exactly one outgoing edge per node. The
    branching is the part that makes this worth being a graph at all, so
    it is asserted structurally rather than only through behaviour."""
    edges = PRE_SCREENING_GRAPH.get_graph().edges
    from_matching = {e.target for e in edges if e.source == "skill_matching"}
    assert from_matching == {"interview_analysis", "__end__"}
    assert {e.conditional for e in edges if e.source == "skill_matching"} == {True}

    from_analysis = {e.target for e in edges if e.source == "interview_analysis"}
    assert from_analysis == {"__end__"}


def test_routing_runs_interview_analysis_when_the_job_has_questions():
    assert _after_skill_matching({"has_questions": True}) == "interview_analysis"


def test_routing_skips_interview_analysis_when_the_job_has_no_questions():
    """Nothing for the Interview Analysis Agent to read — it must be
    skipped, not run against an empty question list."""
    assert _after_skill_matching({"has_questions": False}) == END


def test_entry_skips_skill_matching_when_the_match_is_already_stored():
    assert _entry({"has_questions": True, "match": object()}) == "interview_analysis"
    assert _entry({"has_questions": False, "match": None}) == "skill_matching"
