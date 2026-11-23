"""Tests for the retrieval automaton -- domain/rag_dfa.py and the graph
it specifies, services/rag_pipeline.py.

Three things pinned here, in order of how badly each would hurt to get
wrong.

First, that the compiled StateGraph *is* the declared automaton. The
table and the graph are two artifacts that have to agree, and nothing
but a test makes them: `add_edge("scoring", "audit")` next to a table
saying scoring goes to audit is exactly the kind of duplication that
silently diverges the first time someone rewires a node. So the edge set
is compared to TRANSITIONS wholesale rather than edge by edge -- an edge
added to one and not the other fails, in both directions.

Second, that the cycle halts. audit -> clarify -> scoring -> audit is
the one path in ARKIVE that can loop, and the Critic that decides
whether to loop is a model. The bound is asserted directly on the
transition function, and then again end-to-end against a Critic stubbed
to reject everything forever, because a bound that only holds in the
unit test is not a bound.

Third, blinding. The Compliance Agent's claim is that names, schools and
graduation years do not reach a model, which is a claim about what is in
a string -- cheap to check, and the sort of thing that quietly stops
being true when someone adds a field to the chunker.

The transition functions take primitives, so their whole input domain
fits in a few lines and they're tested directly rather than through runs
of the real agents.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from langchain_openai import OpenAIEmbeddings
from langgraph.graph import END as LANGGRAPH_END

import openai

from app.domain import rag_dfa
from app.models.application_resume import ApplicationResume
from app.schemas.skill_match import AuditVerdict, SkillMatchAnalysis
from app.schemas.skill_match import RecheckResult, VerdictAuditResult
from app.services import rag_pipeline
from app.services.agents.rag_catalog import (
    COMPLIANCE,
    RAG_AGENTS,
    VALIDATION,
    _expand_queries as rc_expand_queries,
    settings as rc_settings,
)


class _FakeOpenAIError(openai.OpenAIError):
    """Minimal OpenAIError subclass, so a test can make the expansion
    call fail without reverse-engineering a real APIError's constructor."""


# ---------------------------------------------------------------------------
# The table itself. Pure data, no graph, no mocking.
# ---------------------------------------------------------------------------


def test_end_sentinel_matches_langgraph():
    """rag_dfa spells END as a literal so the pure core imports no graph
    runtime for one constant. This is the check that buys back what the
    duplication costs -- a rename upstream fails here instead of
    producing a graph with an edge to a node that doesn't exist."""
    assert rag_dfa.END == LANGGRAPH_END


def test_every_state_is_reachable():
    """An agent the table can never route to is a bug every time --
    either a typo in a successor set or an orphaned node."""
    assert rag_dfa.unreachable_states() == frozenset()


def test_terminal_states_only_lead_to_end():
    for state in rag_dfa.TERMINAL:
        assert rag_dfa.TRANSITIONS[state] == frozenset({rag_dfa.END})


def test_the_automaton_has_exactly_one_cycle_back_to_scoring():
    """The clarify retry. Asserted because it's the property that makes
    this a DFA with a loop rather than a DAG, and the only reason the
    halting argument is needed at all."""
    assert "scoring" in rag_dfa.TRANSITIONS["clarify"]
    assert "clarify" in rag_dfa.TRANSITIONS["audit"]
    assert "audit" in rag_dfa.TRANSITIONS["scoring"]
    # audit can also bail straight to manual_review without entering the
    # cycle, which is what keeps a degenerate JD cheap
    assert "manual_review" in rag_dfa.TRANSITIONS["audit"]


def test_scoring_is_unreachable_without_compliance():
    """The blinding pass cannot be skipped on the way in. Both routes to
    scoring -- the first pass and the clarify retry -- come from states
    that are themselves only reachable after compliance has run."""
    into_scoring = {s for s, targets in rag_dfa.TRANSITIONS.items() if "scoring" in targets}
    assert into_scoring == {"context_routing", "clarify"}
    into_context_routing = {
        s for s, targets in rag_dfa.TRANSITIONS.items() if "context_routing" in targets
    }
    assert into_context_routing == {"compliance"}


# ---------------------------------------------------------------------------
# δ — the transition functions, over their whole input domain.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "has_usable_evidence,expected",
    [(True, "compliance"), (False, "rejected")],
)
def test_after_validation(has_usable_evidence, expected):
    assert rag_dfa.after_validation(has_usable_evidence=has_usable_evidence) == expected


@pytest.mark.parametrize(
    "is_grounded,can_retry,expected",
    [
        (True, True, rag_dfa.END),
        (True, False, rag_dfa.END),
        (False, True, "clarify"),
        # the case real data exposed: the Critic objected, but the
        # requisition had no parsed requirements, so every retry would
        # re-query the same 2000-character blob. Stop instead of spending
        # the budget rediscovering that.
        (False, False, "manual_review"),
    ],
)
def test_after_audit(is_grounded, can_retry, expected):
    assert rag_dfa.after_audit(is_grounded=is_grounded, can_retry=can_retry) == expected


def test_a_grounded_assessment_ends_regardless_of_whether_retry_was_possible():
    """can_retry only gates the *failure* branch -- it must never turn an
    accepted assessment into a manual review."""
    assert rag_dfa.after_audit(is_grounded=True, can_retry=False) == rag_dfa.END


def test_after_clarify_buys_exactly_max_clarify_loops_rewrites():
    """The constant is counted in rewrites, so each of the first
    MAX_CLARIFY_LOOPS visits must route back to scoring and the one
    after it must not. Off by one in either direction is either a
    wasted pair of model calls per rejected application or a budget
    that is half what it claims."""
    for visit in range(1, rag_dfa.MAX_CLARIFY_LOOPS + 1):
        assert rag_dfa.after_clarify(clarify_loops=visit) == "scoring"
    assert rag_dfa.after_clarify(clarify_loops=rag_dfa.MAX_CLARIFY_LOOPS + 1) == "manual_review"
    assert rag_dfa.after_clarify(clarify_loops=rag_dfa.MAX_CLARIFY_LOOPS + 99) == "manual_review"


# ---------------------------------------------------------------------------
# The graph against the table.
# ---------------------------------------------------------------------------


def _compiled_edges() -> dict[str, set[str]]:
    """The compiled graph's edges as {source: {targets}}, minus the
    START edge, which the table doesn't model (a DFA's start state is
    named, not pointed at)."""
    edges: dict[str, set[str]] = {}
    for edge in rag_pipeline.RAG_GRAPH.get_graph().edges:
        if edge.source == "__start__":
            continue
        edges.setdefault(edge.source, set()).add(edge.target)
    return edges


def test_graph_declares_a_node_for_every_state():
    nodes = set(rag_pipeline.RAG_GRAPH.get_graph().nodes)
    assert set(rag_dfa.TRANSITIONS) <= nodes


def test_graph_edges_are_exactly_the_declared_transitions():
    """The one that keeps the specification honest. Compared as whole
    mappings so a stray edge fails as loudly as a missing one."""
    declared = {source: set(targets) for source, targets in rag_dfa.TRANSITIONS.items()}
    assert _compiled_edges() == declared


def test_graph_starts_at_the_declared_start_state():
    edges = rag_pipeline.RAG_GRAPH.get_graph().edges
    assert any(e.source == "__start__" and e.target == rag_dfa.START_STATE for e in edges)


def test_every_non_terminal_state_has_an_agent():
    """Each state does someone's work, and the two that don't are the
    dead ends -- which is the whole reason they aren't agents."""
    agent_names = {agent.name for agent in RAG_AGENTS}
    assert agent_names == set(rag_dfa.TRANSITIONS) - rag_dfa.TERMINAL


def test_sub_agent_names_match_their_graph_nodes():
    nodes = set(rag_pipeline.RAG_GRAPH.get_graph().nodes)
    for agent in RAG_AGENTS:
        assert agent.name in nodes, f"{type(agent).__name__} declares a name with no node"


# ---------------------------------------------------------------------------
# The Compliance Agent's actual claim.
# ---------------------------------------------------------------------------


def _blinded(chunks: list[str], **resume_fields) -> tuple[list[str], int]:
    defaults = dict(
        full_name="Juan Dela Cruz",
        email="juan@example.com",
        phone="09171234567",
        location="Lucena City",
        linkedin_url="",
        portfolio_url="",
        education=[{"school": "Manuel S. Enverga University", "degree": "BS"}],
    )
    defaults.update(resume_fields)
    resume = SimpleNamespace(**defaults)
    out = COMPLIANCE.run({"resume_chunks": chunks}, {"resume": resume})
    return out["redacted_chunks"], out["redactions"]


def test_compliance_removes_name_school_and_graduation_year():
    chunks, count = _blinded(
        [
            "Juan Dela Cruz — Backend Engineer",
            "BS in Computer Science, Manuel S. Enverga University, 2019",
        ]
    )
    joined = " ".join(chunks)
    assert "Juan" not in joined and "Dela Cruz" not in joined
    assert "Enverga" not in joined
    assert "2019" not in joined
    assert count > 0


def test_compliance_keeps_the_evidence_it_is_supposed_to_keep():
    """Blinding that removed employers and skills would leave nothing to
    evaluate -- the point is skill-first screening, not no screening."""
    chunks, _ = _blinded(["Backend Engineer at Acme Corp: built APIs with Python and FastAPI"])
    assert "Acme Corp" in chunks[0]
    assert "Python" in chunks[0] and "FastAPI" in chunks[0]
    assert "Backend Engineer" in chunks[0]


def test_compliance_leaves_non_year_numbers_alone():
    """The year pattern is anchored on 19xx/20xx precisely so quantified
    impact statements -- the most valuable evidence on a resume -- survive."""
    chunks, _ = _blinded(["Processed 3000 records per second across 1200 nodes"])
    assert "3000" in chunks[0] and "1200" in chunks[0]


def test_compliance_redacts_the_longest_span_first():
    """Redacting a substring before the longer span containing it leaves
    the tail behind -- "[REDACTED] University" still names the school."""
    chunks, _ = _blinded(
        ["Studied at Enverga University"],
        education=[{"school": "Enverga University"}],
        full_name="Enverga",
    )
    assert "University" not in chunks[0]


def test_validation_rejects_an_empty_corpus():
    assert VALIDATION.run({"resume_chunks": []}, {})["has_usable_evidence"] is False
    assert VALIDATION.run({"resume_chunks": ["  ", ""]}, {})["has_usable_evidence"] is False
    assert VALIDATION.run({"resume_chunks": ["Engineer at Acme"]}, {})["has_usable_evidence"] is True


# ---------------------------------------------------------------------------
# End to end, with the models stubbed. The halting proof.
# ---------------------------------------------------------------------------


def _resume(**overrides) -> ApplicationResume:
    defaults = dict(
        original_filename="r.pdf",
        stored_path="/tmp/r.pdf",
        full_name="Juan Dela Cruz",
        email="juan@example.com",
        phone="",
        location="",
        linkedin_url="",
        portfolio_url="",
        experience=[{"title": "Backend Engineer", "company": "Acme", "description": "Built APIs"}],
        education=[{"degree": "BS", "field_of_study": "CS", "school": "Enverga"}],
        skills=["Python", "FastAPI"],
        certifications=[],
        raw_extracted_text="Backend Engineer with Python.",
    )
    defaults.update(overrides)
    return ApplicationResume(**defaults)


def _requisition():
    return SimpleNamespace(
        id=1,
        title="Backend Engineer",
        department="Engineering",
        description="",
        qualifications="Experience with Python",
        requirements="Experience with FastAPI",
    )


def _llm_returning(*, verdict: AuditVerdict) -> MagicMock:
    """A ChatOpenAI stub that answers each structured-output request with
    something of the right type -- one shared mock would hand the Critic
    a SkillMatchAnalysis and vice versa."""
    analysis = SkillMatchAnalysis(
        strengths=["Has Python experience"],
        gaps=["No cloud certifications"],
        summary="A reasonable fit.",
    )
    by_schema = {"SkillMatchAnalysis": analysis, "AuditVerdict": verdict, "VerdictAuditResult": VerdictAuditResult(), "RecheckResult": RecheckResult()}

    llm = MagicMock()
    llm.with_structured_output.side_effect = lambda schema, **kw: SimpleNamespace(
        invoke=lambda messages: by_schema[schema.__name__]
    )
    return llm


@pytest.fixture
def embeddings():
    """A real OpenAIEmbeddings with its two network calls patched out.

    Not a MagicMock: _EmbeddingSimilarityRetriever is a Pydantic model
    whose `embeddings` field is typed as OpenAIEmbeddings, so a mock is
    rejected at construction. Patching the methods on the class is what
    the rest of the suite does, for the same reason."""
    with (
        patch.object(
            OpenAIEmbeddings,
            "embed_documents",
            side_effect=lambda texts: [[1.0, 0.0, 0.0] for _ in texts],
        ),
        patch.object(OpenAIEmbeddings, "embed_query", return_value=[1.0, 0.0, 0.0]),
    ):
        yield OpenAIEmbeddings(model="text-embedding-3-small", api_key="test-key")


def test_clean_run_stops_at_audit_without_clarifying(embeddings):
    analysis, trace = rag_pipeline.run_rag_analysis(
        llm=_llm_returning(verdict=AuditVerdict(is_grounded=True)),
        embeddings=embeddings,
        resume=_resume(),
        requisition=_requisition(),
        combined_score=72.0,
    )
    assert trace.terminal_state == "audit"
    assert trace.clarify_loops == 0
    assert trace.path == ["ingestion", "validation", "compliance", "context_routing", "scoring", "audit"]
    assert analysis.summary == "A reasonable fit."
    assert trace.redactions > 0


def test_a_permanently_unsatisfied_critic_terminates_in_manual_review(embeddings):
    """The halting proof. This Critic rejects every draft it is ever
    shown; without the budget the graph would cycle until LangGraph's own
    recursion limit killed it mid-request."""
    verdict = AuditVerdict(
        is_grounded=False,
        unsupported_claims=["Has Python experience"],
        needs_more_context=["Experience with Python"],
        note="Nothing supports this.",
    )
    analysis, trace = rag_pipeline.run_rag_analysis(
        llm=_llm_returning(verdict=verdict),
        embeddings=embeddings,
        resume=_resume(),
        requisition=_requisition(),
        combined_score=72.0,
    )
    assert trace.terminal_state == "manual_review"
    # MAX_CLARIFY_LOOPS rewrites bought, plus the visit that found the
    # budget spent and routed here
    assert trace.clarify_loops == rag_dfa.MAX_CLARIFY_LOOPS + 1
    # the first draft, then one rewrite per rewrite bought
    assert trace.path.count("scoring") == rag_dfa.MAX_CLARIFY_LOOPS + 1
    assert trace.path[-1] == "manual_review"
    assert trace.degraded_reason


def test_manual_review_strips_the_claims_the_critic_rejected(embeddings):
    """An assessment the Critic refused to sign off must not reach HR
    looking identical to one it approved."""
    verdict = AuditVerdict(is_grounded=False, unsupported_claims=["Has Python experience"])
    analysis, trace = rag_pipeline.run_rag_analysis(
        llm=_llm_returning(verdict=verdict),
        embeddings=embeddings,
        resume=_resume(),
        requisition=_requisition(),
        combined_score=72.0,
    )
    assert "Has Python experience" not in analysis.strengths
    assert analysis.summary.startswith("[Unverified")


def test_an_unreadable_resume_dead_ends_before_any_model_call(embeddings):
    """The validation gate, and the reason it is placed where it is: a
    corpus with nothing in it costs zero tokens to reject."""
    llm = _llm_returning(verdict=AuditVerdict(is_grounded=True))
    empty = _resume(experience=[], education=[], skills=[], certifications=[], raw_extracted_text="")

    analysis, trace = rag_pipeline.run_rag_analysis(
        llm=llm,
        embeddings=embeddings,
        resume=empty,
        requisition=_requisition(),
        combined_score=30.0,
    )
    assert trace.terminal_state == "rejected"
    assert trace.path == ["ingestion", "validation", "rejected"]
    llm.with_structured_output.assert_not_called()
    assert analysis.strengths == []
    assert "human review" in analysis.summary


def test_the_dead_end_is_not_a_rejection_of_the_candidate(embeddings):
    """`rejected` is the automaton's name for a state, and the diagram's.
    What it must not become is an automated refusal -- the pipeline has
    no authority to turn an unparseable PDF into a hiring decision."""
    _, trace = rag_pipeline.run_rag_analysis(
        llm=_llm_returning(verdict=AuditVerdict(is_grounded=True)),
        embeddings=embeddings,
        resume=_resume(experience=[], education=[], skills=[], certifications=[], raw_extracted_text=""),
        requisition=_requisition(),
        combined_score=30.0,
    )
    assert "résumé" in trace.degraded_reason.lower() or "resume" in trace.degraded_reason.lower()


# ---------------------------------------------------------------------------
# LLM query expansion — settings.rag_query_expansion.
#
# The flag exists to be measured, so what matters is that "off" is
# genuinely the old behavior (no extra call, identical retrieval), that
# "on" actually reaches retrieval, and that a failed expansion degrades
# instead of taking pre-screening down with it.
# ---------------------------------------------------------------------------


def _expansion_llm(probes: dict[str, list[str]], *, verdict=None, fail=False):
    """A ChatOpenAI stub that answers QueryExpansion with `probes` and
    still serves the scoring/audit calls around it."""
    from app.schemas.skill_match import QueryExpansion, RequirementProbes

    probes = probes or {}

    results = {
        "SkillMatchAnalysis": SkillMatchAnalysis(strengths=["s"], gaps=["g"], summary="ok"),
        "AuditVerdict": verdict if verdict is not None else AuditVerdict(is_grounded=True),
        "VerdictAuditResult": VerdictAuditResult(), "RecheckResult": RecheckResult(),
        "QueryExpansion": QueryExpansion(
            expansions=[RequirementProbes(requirement=r, probes=p) for r, p in probes.items()]
        ),
    }
    calls: list[str] = []

    def _structured(schema, **kw):
        calls.append(schema.__name__)
        if fail and schema.__name__ == "QueryExpansion":
            raise _FakeOpenAIError("expansion is down")
        return SimpleNamespace(invoke=lambda messages: results[schema.__name__])

    llm = MagicMock()
    llm.with_structured_output.side_effect = _structured
    llm.calls = calls
    return llm


def test_expansion_off_makes_no_extra_model_call(embeddings, monkeypatch):
    monkeypatch.setattr(rc_settings, "rag_query_expansion", False)
    llm = _expansion_llm({})

    _, trace = rag_pipeline.run_rag_analysis(
        llm=llm, embeddings=embeddings, resume=_resume(), requisition=_requisition(), combined_score=72.0
    )
    assert "QueryExpansion" not in llm.calls
    # plus the Verdict Auditor, which reviews the verdicts on their own
    # after the automaton halts (rag_pipeline._settle_verdicts), and the
    # routine second reading every not_met gets -- the stub analysis
    # gives no verdicts, so each requirement stands as not_met
    assert llm.calls == ["SkillMatchAnalysis", "AuditVerdict", "VerdictAuditResult", "RecheckResult"]
    assert trace.expanded_queries is False


def test_expansion_on_adds_exactly_one_call_and_is_recorded(embeddings, monkeypatch):
    monkeypatch.setattr(rc_settings, "rag_query_expansion", True)
    llm = _expansion_llm(
        {
            "Experience with Python": ["built REST APIs in Python", "shipped Django services"],
            "Experience with FastAPI": ["authored FastAPI endpoints"],
        }
    )

    _, trace = rag_pipeline.run_rag_analysis(
        llm=llm, embeddings=embeddings, resume=_resume(), requisition=_requisition(), combined_score=72.0
    )
    # one expansion for the whole JD, not one per requirement
    assert llm.calls.count("QueryExpansion") == 1
    assert llm.calls[0] == "QueryExpansion"
    assert trace.expanded_queries is True


def test_a_failed_expansion_degrades_instead_of_failing_pre_screening(embeddings, monkeypatch):
    """Turning the flag on must not be able to make pre-screening less
    available than leaving it off -- expansion is an enhancement to
    retrieval, never a precondition for it."""
    monkeypatch.setattr(rc_settings, "rag_query_expansion", True)
    llm = _expansion_llm({"Experience with Python": ["x"]}, fail=True)

    analysis, trace = rag_pipeline.run_rag_analysis(
        llm=llm, embeddings=embeddings, resume=_resume(), requisition=_requisition(), combined_score=72.0
    )
    assert trace.terminal_state == "audit"
    assert trace.expanded_queries is False
    assert analysis.summary == "ok"


def test_probes_for_a_reworded_requirement_are_dropped(monkeypatch):
    """The model is told to copy the requirement verbatim because it is a
    join key. One that tidies the wording loses its probes rather than
    having them attached to the wrong requirement."""
    monkeypatch.setattr(rc_settings, "rag_query_expansion", True)
    llm = _expansion_llm({"Experience with python programming": ["built REST APIs"]})

    probes = rc_expand_queries(llm, ["Experience with Python"], "Backend Engineer, Engineering")
    assert probes == {}


def test_expanded_retrieval_still_includes_the_plain_requirement_query(embeddings):
    """Probes add rankings, they never replace the original query -- which
    is what makes a bad expansion dilute rather than decide."""
    from app.services.skill_matching import _retrieve_with_query_variants

    chunks = ["Backend Engineer at Acme: built APIs with Python", "Certification: AWS"]
    only_plain = _retrieve_with_query_variants(
        embeddings, chunks, {"Python": ["Python"]}, top_k=2, doc_embeddings=[[1.0, 0.0, 0.0]] * 2
    )
    with_probes = _retrieve_with_query_variants(
        embeddings,
        chunks,
        {"Python": ["Python", "built REST APIs", "shipped services"]},
        top_k=2,
        doc_embeddings=[[1.0, 0.0, 0.0]] * 2,
    )
    assert only_plain["Python"], "the plain query alone must still retrieve"
    assert with_probes["Python"], "probes must not empty the result"
    assert set(only_plain["Python"]) <= set(chunks)


def test_fuse_rankings_generalizes_ensemble_rank():
    """_ensemble_rank is now the two-list case of _fuse_rankings; the
    existing two-list behavior must be untouched by the generalization."""
    from app.services.skill_matching import _ensemble_rank, _fuse_rankings
    from langchain_core.documents import Document

    a, b, c = Document(page_content="A"), Document(page_content="B"), Document(page_content="C")
    assert [d.page_content for d in _ensemble_rank([a, b], [b, c], k=2)] == [
        d.page_content for d in _fuse_rankings([[a, b], [b, c]], k=2)
    ]
    # a doc surfaced by three probes outranks one surfaced by a single
    # first-place hit -- the property multi-query retrieval relies on
    fused = _fuse_rankings([[a, b], [b], [b]], k=2)
    assert fused[0].page_content == "B"


def test_terminal_states_are_exactly_what_skill_matching_treats_as_unverified():
    """run_skill_matching flags on `rag_trace.terminal_state in TERMINAL`
    rather than on a list of its own. Pinned so adding a third dead end
    to the automaton cannot quietly stop escalating -- a new state joins
    TERMINAL and the flag follows it."""
    from app.services.skill_matching import UNVERIFIED_TERMINAL_STATES

    assert UNVERIFIED_TERMINAL_STATES is rag_dfa.TERMINAL
    assert "audit" not in UNVERIFIED_TERMINAL_STATES


def test_the_scoring_agent_never_sees_the_unredacted_resume(embeddings):
    """The end-to-end version of the blinding claim: whatever reaches a
    model on the real path carries no name and no school."""
    captured: list[str] = []
    verdict = AuditVerdict(is_grounded=True)

    analysis = SkillMatchAnalysis(strengths=[], gaps=[], summary="ok")
    by_schema = {"SkillMatchAnalysis": analysis, "AuditVerdict": verdict, "VerdictAuditResult": VerdictAuditResult(), "RecheckResult": RecheckResult()}

    def _capture(messages):
        captured.extend(m["content"] for m in messages)
        return by_schema[_capture.schema]

    llm = MagicMock()

    def _structured(schema, **kw):
        _capture.schema = schema.__name__
        return SimpleNamespace(invoke=_capture)

    llm.with_structured_output.side_effect = _structured

    rag_pipeline.run_rag_analysis(
        llm=llm,
        embeddings=embeddings,
        resume=_resume(),
        requisition=_requisition(),
        combined_score=72.0,
    )
    prompts = " ".join(captured)
    assert "Juan" not in prompts
    assert "Dela Cruz" not in prompts
    assert "Enverga" not in prompts
    # the evidence itself still got through
    assert "Acme" in prompts


def test_a_requisition_with_no_requirements_skips_the_clarify_cycle(embeddings):
    """A job with no listed requirements must not spend the clarify budget.

    Found on real data, not in a test: four of eight open requisitions
    had empty qualifications *and* requirements, so retrieval fell back
    to one 2000-character prose blob, the Critic rightly objected, and
    the clarify cycle then spent the whole budget widening k over a
    single query that could never yield anything better. Six model calls
    and 12-17 seconds to land where the first two already were -- past
    the applicant-facing client's 15s abort.
    """
    verdict = AuditVerdict(is_grounded=False, unsupported_claims=["Has Python experience"])
    bare = _requisition()
    bare.qualifications = ""
    bare.requirements = ""
    bare.description = "We are hiring a backend engineer to join the team."
    llm = _expansion_llm({}, verdict=verdict)

    analysis, trace = rag_pipeline.run_rag_analysis(
        llm=llm, embeddings=embeddings, resume=_resume(), requisition=bare, combined_score=72.0
    )

    assert trace.terminal_state == "manual_review"
    assert trace.clarify_loops == 0, "the cycle must not run at all"
    assert "clarify" not in trace.path
    assert trace.path.count("scoring") == 1, "exactly one draft, not one per retry"
    assert "qualifications or requirements" in trace.degraded_reason
    # the cost claim, directly: one scoring call and one audit call
    # plus the Verdict Auditor, which reviews the verdicts on their own
    # after the automaton halts (rag_pipeline._settle_verdicts), and the
    # routine second reading every not_met gets -- the stub analysis
    # gives no verdicts, so each requirement stands as not_met
    assert llm.calls == ["SkillMatchAnalysis", "AuditVerdict", "VerdictAuditResult", "RecheckResult"]


def test_a_requisition_with_requirements_still_gets_its_retries(embeddings):
    """The guard must not suppress retries where they can actually help."""
    verdict = AuditVerdict(
        is_grounded=False,
        unsupported_claims=["Has Python experience"],
        needs_more_context=["Experience with Python"],
    )
    _, trace = rag_pipeline.run_rag_analysis(
        llm=_llm_returning(verdict=verdict),
        embeddings=embeddings,
        resume=_resume(),
        requisition=_requisition(),
        combined_score=72.0,
    )
    assert trace.clarify_loops == rag_dfa.MAX_CLARIFY_LOOPS + 1
    assert trace.path.count("scoring") == rag_dfa.MAX_CLARIFY_LOOPS + 1


def test_expansion_is_skipped_when_the_jd_has_no_requirements(embeddings, monkeypatch):
    """Probes are written per requirement. Asked to expand a single
    2000-character blob a model either rewords it -- losing the join key
    and producing nothing -- or latches onto one fragment. Measured on
    real data: zero usable probes, five seconds spent."""
    monkeypatch.setattr(rc_settings, "rag_query_expansion", True)
    bare = _requisition()
    bare.qualifications = ""
    bare.requirements = ""
    bare.description = "We are hiring a backend engineer."
    llm = _expansion_llm({}, verdict=AuditVerdict(is_grounded=True))

    _, trace = rag_pipeline.run_rag_analysis(
        llm=llm, embeddings=embeddings, resume=_resume(), requisition=bare, combined_score=72.0
    )
    assert "QueryExpansion" not in llm.calls
    assert trace.expanded_queries is False


# ---------------------------------------------------------------------------
# The Critic's per-claim rulings, and what the retry is told.
# ---------------------------------------------------------------------------

from app.schemas.skill_match import ClaimReview, RequirementCheck  # noqa: E402
from app.services.agents import rag_catalog  # noqa: E402

_DRAFT = SkillMatchAnalysis(
    strengths=["Knows Python, Java and C++.", "Mentored a top-ten coding team."],
    gaps=["No evidence of open source work.", "No evidence of C++."],
    summary="",
)


def test_the_critics_rulings_decide_the_verdict_not_its_loose_list():
    """A claim listed as unsupported that the Critic's own ruling, with a
    reason, accepted. The rulings win, labels resolve to the claims'
    own text, and a verdict-line objection -- which has no ruling -- stands."""
    verdict = AuditVerdict(
        is_grounded=False,
        claim_reviews=[
            ClaimReview(claim="S1", requirement="Programming languages", reason="Skills list names all three.", accurate=True),
            ClaimReview(claim="S2", requirement="Student success", reason="4 of 5 ranked top ten.", accurate=True),
            ClaimReview(claim="G1", requirement="Open source", reason="Nothing mentions open source.", accurate=True),
            ClaimReview(claim="G2", requirement="Programming languages", reason="The skills list names C++.", accurate=False),
        ],
        unsupported_claims=["- Knows Python, Java and C++", "[met] Bachelor's degree — quoted evidence: (none)"],
    )
    settled = rag_catalog._settled_verdict(verdict, _DRAFT)

    assert settled.unsupported_claims == ["No evidence of C++.", "[met] Bachelor's degree — quoted evidence: (none)"]
    assert settled.is_grounded is False
    assert [r.claim for r in settled.claim_reviews][:2] == _DRAFT.strengths


def test_rulings_that_accept_everything_sign_the_assessment_off():
    verdict = AuditVerdict(
        is_grounded=False,
        claim_reviews=[ClaimReview(claim=label, accurate=True) for label in ("S1", "S2", "G1", "G2")],
        unsupported_claims=["Knows Python, Java and C++."],
    )
    settled = rag_catalog._settled_verdict(verdict, _DRAFT)
    assert settled.is_grounded is True
    assert settled.unsupported_claims == []


def test_a_verdict_without_rulings_is_left_as_the_critic_gave_it():
    verdict = AuditVerdict(is_grounded=False, unsupported_claims=["Knows Python, Java and C++."])
    assert rag_catalog._settled_verdict(verdict, _DRAFT) == verdict


def test_a_retry_is_shown_its_draft_and_told_to_change_only_what_was_rejected():
    state = {
        "analysis": _DRAFT.model_dump(),
        "verdict": {
            "claim_reviews": [{"claim": "No evidence of C++.", "reason": "The skills list names C++.", "accurate": False}]
        },
    }
    request = rag_catalog._rewrite_request(state, ["No evidence of C++."])

    assert "- Knows Python, Java and C++." in request
    assert "- No evidence of C++.   [REJECTED]" in request
    assert "Reason: The skills list names C++." in request
    assert "Keep every claim that was not rejected exactly as it was" in request


def test_clarify_adds_to_a_requirements_evidence_instead_of_replacing_it(embeddings):
    """Reformulated probes rank differently; replacing the evidence dropped
    the chunk a claim was quoting, and the Critic then asked for more
    context on a requirement the resume plainly met."""
    state = {
        "verdict": AuditVerdict(is_grounded=False, needs_more_context=["Experience with Python"]).model_dump(),
        "requirements": ["Experience with Python", "Experience with FastAPI"],
        "redacted_chunks": ["Skills: Python, FastAPI", "Backend Engineer at Acme: Built APIs"],
        "chunk_sections": ["skills", "experience"],
        "evidence": [
            {"requirement": "Experience with Python", "evidence": ["Skills: Python, FastAPI"]},
            {"requirement": "Experience with FastAPI", "evidence": ["Skills: Python, FastAPI"]},
        ],
        "clarify_loops": 0,
    }
    ctx = {"llm": MagicMock(), "embeddings": embeddings, "requisition": _requisition()}
    with patch.object(rag_catalog.settings, "rag_query_expansion", False):
        out = rag_catalog.CLARIFY.run(state, ctx)

    python = next(e for e in out["evidence"] if e["requirement"] == "Experience with Python")
    assert python["evidence"][0] == "Skills: Python, FastAPI"
    assert "Backend Engineer at Acme: Built APIs" in python["evidence"]


def test_a_gap_about_a_requirement_settled_as_met_is_dropped():
    """A gap beside a re-checked, verified `met` for its requirement is
    dropped. Which requirement a gap is about is
    the Critic's ruling, so a gap it did not tie to one stays."""
    state = {
        "verdict": {
            "claim_reviews": [
                {"claim": "No evidence of a track record.", "requirement": "Student success", "accurate": True},
                {"claim": "No evidence of open source work.", "requirement": "Open source", "accurate": True},
            ]
        }
    }
    checks = [
        RequirementCheck(requirement="Student success", verdict="met", evidence_quote="4 of 5 ranked", verified=True),
        RequirementCheck(requirement="Open source", verdict="not_met", evidence_quote=""),
    ]
    assert rag_pipeline._answered_gaps(state, checks) == {rag_catalog._claim_key("No evidence of a track record.")}
