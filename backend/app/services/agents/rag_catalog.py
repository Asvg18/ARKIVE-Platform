"""The seven sub-agents of the Skill Matching Agent's retrieval pipeline,
and the two verdict agents run on its result.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

import openai

from app.domain.rag_dfa import MAX_CLARIFY_LOOPS
from app.infra.config import settings
from app.schemas.skill_match import (
    AuditVerdict,
    QueryExpansion,
    RecheckResult,
    RequirementCheck,
    RetrievedEvidence,
    SkillMatchAnalysis,
    VerdictAuditResult,
)
from app.services.agents.base import SubAgent
from app.services.pdf_text import AIExtractionFailedError

__all__ = [
    "AUDIT",
    "CLARIFY",
    "COMPLIANCE",
    "CONTEXT_ROUTING",
    "INGESTION",
    "RAG_AGENTS",
    "RAG_BY_NAME",
    "SCORING",
    "VALIDATION",
    "VERDICT_AGENTS",
    "VERDICT_AUDIT",
    "VERDICT_RECHECK",
]

_log = logging.getLogger(__name__)

# Same wording the single-call version raised, kept identical so the
# applicant-facing copy doesn't change just because the internals did.
_FAILURE_MESSAGE = (
    "Pre-screening could not be completed, so your answers were not "
    "submitted. Please try again shortly. If it keeps happening, contact "
    "the HR office."
)

# Graduation years only (19xx/20xx), so "Processed 3000 records" stays.
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")

# How much wider the Clarify Agent looks on a retry: missed evidence is
# usually a top-k problem, so it looks further down the ranking.
_CLARIFY_K_BONUS = 3


def _invoke_structured(llm, schema, messages):
    """Every model call in this pipeline goes through here: OpenAI errors
    and a None parse both raise AIExtractionFailedError (502). A node must
    never swallow one and carry on with no evidence."""
    try:
        parsed = llm.with_structured_output(schema, method="json_schema").invoke(messages)
    except openai.OpenAIError as exc:
        raise AIExtractionFailedError(_FAILURE_MESSAGE) from exc
    if parsed is None:
        raise AIExtractionFailedError(_FAILURE_MESSAGE)
    return parsed


_EXPANSION_SYSTEM_PROMPT = (
    "You write search queries that will be run against a candidate's "
    "résumé by keyword (BM25) and semantic search. For each job "
    "requirement you are given, write short probes phrased the way "
    "evidence actually appears on a résumé — past-tense accomplishments, "
    "concrete tools, job titles, artifacts — never as questions, and "
    "never by restating the requirement. 'Strong communication skills' "
    "should yield probes like 'presented findings to stakeholders', "
    "'authored technical documentation', 'facilitated weekly standups'. "
    "Each probe should cover a genuinely different way a candidate might "
    "evidence the requirement, not one idea reworded. Return every "
    "requirement you were given, copying its original text into "
    "`requirement` character for character — it is a join key, not "
    "something to tidy up."
)

_CLARIFY_EXPANSION_SUFFIX = (
    "\n\nA reviewer has just rejected an assessment built on the evidence "
    "retrieved for these requirements, saying it was unsupported or too "
    "thin to judge. Your previous probes did not surface what was needed. "
    "Write different ones: attack the requirement from angles you have "
    "not tried — adjacent tooling, the artifacts the work produces, the "
    "titles people doing it hold, the problems it solves. Do not repeat "
    "the requirement's own wording."
)

#: Probes requested per requirement; a fourth rarely finds anything new,
#: and each costs a BM25 and a cosine pass.
_PROBES_PER_REQUIREMENT = 3


def _expand_queries(
    llm,
    requirements: list[str],
    role_context: str,
    *,
    objections: AuditVerdict | None = None,
) -> dict[str, list[str]]:
    """One model call turning every requirement into retrieval probes.

    Returns {requirement: [probe, ...]}, or an empty dict on any failure:
    expansion is optional, so it must never make pre-screening fail, and
    callers fall back to the plain requirement query. Probes are matched
    back by exact requirement text; a reworded requirement loses its
    probes rather than attaching them to the wrong one.
    """
    if not requirements:
        return {}

    instructions = _EXPANSION_SYSTEM_PROMPT + (_CLARIFY_EXPANSION_SUFFIX if objections else "")
    user_content = (
        f"Role: {role_context}\n\n"
        f"Write up to {_PROBES_PER_REQUIREMENT} probes for each of these requirements:\n"
        + "\n".join(f"- {req}" for req in requirements)
    )
    if objections is not None:
        if objections.needs_more_context:
            user_content += "\n\nToo thin to judge:\n" + "\n".join(
                f"- {item}" for item in objections.needs_more_context
            )
        if objections.unsupported_claims:
            user_content += "\n\nClaims the reviewer could not support:\n" + "\n".join(
                f"- {claim}" for claim in objections.unsupported_claims
            )

    try:
        expansion = _invoke_structured(
            llm,
            QueryExpansion,
            [
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_content},
            ],
        )
    except AIExtractionFailedError:
        _log.warning("Query expansion failed; falling back to plain requirement queries", exc_info=True)
        return {}

    wanted = set(requirements)
    probes: dict[str, list[str]] = {}
    for item in expansion.expansions:
        if item.requirement in wanted:
            cleaned = [p.strip() for p in item.probes if p and p.strip()]
            if cleaned:
                probes[item.requirement] = cleaned[:_PROBES_PER_REQUIREMENT]
    _log.info("Query expansion produced probes for %s/%s requirements", len(probes), len(requirements))
    return probes


class IngestionAgent(SubAgent):
    """Turns the reviewed resume fields into the retrieval corpus:
    experience entries, education entries, skills in groups of four, one
    chunk per certification. Chunking the structured fields, not the raw
    PDF text, keeps a two-column layout from interleaving lines."""

    name = "ingestion"
    label = "Ingestion & Structuring Agent"
    duty = "Converts the resume into clean, retrievable evidence chunks."

    def run(self, state: Mapping[str, Any], ctx: Mapping[str, Any]) -> dict[str, Any]:
        from app.services.skill_matching import _fallback_resume_chunks, _labelled_resume_evidence

        resume = ctx["resume"]
        labelled = _labelled_resume_evidence(resume)
        structured = [text for _, text in labelled]
        # raw paragraphs only when every structured field is blank
        chunks = structured or _fallback_resume_chunks(resume)
        return {
            "resume_chunks": chunks,
            # which section each chunk came from, aligned with
            # resume_chunks; empty for the raw-text fallback, which has none
            "chunk_sections": [section for section, _ in labelled] if structured else [],
            "structured_chunk_count": len(structured),
            "path": ["ingestion"],
        }


class ValidationAgent(SubAgent):
    """Decides whether there is anything to retrieve over. An empty corpus
    stops here, before any model call, rather than producing an
    assessment with no evidence behind it."""

    name = "validation"
    label = "Validation Agent"
    duty = "Gates the pipeline on whether the resume yielded usable evidence."

    def run(self, state: Mapping[str, Any], ctx: Mapping[str, Any]) -> dict[str, Any]:
        chunks = state.get("resume_chunks") or []
        has_usable_evidence = any(chunk.strip() for chunk in chunks)
        return {"has_usable_evidence": has_usable_evidence, "path": ["validation"]}


class ComplianceAgent(SubAgent):
    """Strips identity from the evidence before any model sees it.

    Removed: the candidate's own name (whole, and token by token, since
    chunks rarely repeat it in full), school names, graduation years,
    and the contact block. Kept: employers, titles, skills, dates of
    *employment* -- those are the evidence, and blinding them would
    leave nothing to evaluate.

    Scope: this blinds the *generative* half (the prose HR reads). The
    numeric score reads skill_matching._resume_scoring_text, which leaves
    out the name and contact block but still includes school names."""

    name = "compliance"
    label = "Compliance & Blind Agent"
    duty = "Redacts names, schools and graduation years from the evidence."

    def run(self, state: Mapping[str, Any], ctx: Mapping[str, Any]) -> dict[str, Any]:
        """Reads `resume_chunks`; returns `redacted_chunks` (identity removed)
        and the `redactions` count. No model call."""
        resume = ctx["resume"]
        chunks: list[str] = state.get("resume_chunks") or []

        # longest first, or "MSEUF" would leave "[SCHOOL] Lucena" behind
        spans: set[str] = set()
        for value in (
            resume.full_name,
            resume.email,
            resume.phone,
            resume.location,
            resume.linkedin_url,
            resume.portfolio_url,
        ):
            if value and len(value.strip()) > 2:
                spans.add(value.strip())
        # individual name tokens -- "Dela Cruz, A." never matches the
        # full_name span but is still identifying
        for token in (resume.full_name or "").split():
            if len(token) > 2:
                spans.add(token.strip(",."))
        for entry in resume.education or []:
            school = (entry.get("school") or "").strip()
            if len(school) > 2:
                spans.add(school)

        redactions = 0
        redacted: list[str] = []
        for chunk in chunks:
            text = chunk
            for span in sorted(spans, key=len, reverse=True):
                pattern = re.compile(re.escape(span), re.IGNORECASE)
                text, count = pattern.subn("[REDACTED]", text)
                redactions += count
            text, year_count = _YEAR_RE.subn("[YEAR]", text)
            redactions += year_count
            redacted.append(text)

        return {"redacted_chunks": redacted, "redactions": redactions, "path": ["compliance"]}


class ContextRouterAgent(SubAgent):
    """Builds the queries and runs hybrid retrieval — the RAG step itself.

    Queries: with settings.rag_query_expansion off (default), each
    requirement plus the job's title and department is one query. With it
    on, one model call also writes probes phrased as resume evidence, and
    each requirement retrieves on its probes *and* its plain query, fused
    together; the plain query is always included, so probes can add
    rankings but never replace them. A failed expansion falls back to the
    plain path.

    Retrieval: BM25 and embedding cosine over the same chunks, fused by
    Reciprocal Rank Fusion. Chunk embeddings are kept in state, so a
    Clarify retry re-ranks without re-embedding."""

    name = "context_routing"
    label = "Context Router Agent"
    duty = "Enriches each requirement and retrieves evidence for it (BM25 + semantic, RRF)."

    def run(self, state: Mapping[str, Any], ctx: Mapping[str, Any]) -> dict[str, Any]:
        """Reads `redacted_chunks` and `chunk_sections`; returns the job's
        `requirements`, the retrieved `evidence` per requirement, the chunk
        embeddings for reuse by Clarify, `jd_has_requirements` and whether
        queries were expanded. A failed expansion falls back to the plain
        requirements; it never fails the run."""
        from app.services.skill_matching import (
            _embed,
            _ensure_section_evidence,
            _retrieve_evidence_for_requirements,
            _retrieve_with_query_variants,
            _RETRIEVAL_TOP_K,
            _target_requirements,
        )

        requisition = ctx["requisition"]
        embeddings = ctx["embeddings"]
        chunks: list[str] = state.get("redacted_chunks") or []

        # the same list the arithmetic half averages over, so every
        # requirement gets both halves of the score
        requirements, jd_has_requirements = _target_requirements(requisition)
        if not jd_has_requirements:
            # No parsed requirement lines: the job's prose becomes a single
            # pseudo-requirement so it is still screenable. A degraded mode:
            # `jd_has_requirements` False skips the clarify cycle
            # (rag_dfa.after_audit) and query expansion below.
            _log.warning(
                "Requisition %s has no parsed qualification/requirement lines; "
                "retrieving against its prose as a single query. Screening quality "
                "for this posting is degraded until HR fills those fields in.",
                getattr(requisition, "id", "?"),
            )

        role_context = f"{requisition.title}, {requisition.department}"
        # query != the requirement itself; the pairing is kept so the
        # Scoring Agent still sees HR's original wording
        queries = {req: f"{req} (for the role: {role_context})" for req in requirements}

        chunk_embeddings = _embed(embeddings, chunks) if chunks else []

        # no expansion on the degraded path: probes for one long blob
        # are unusable (and a reworded blob loses its join key)
        probes = (
            _expand_queries(ctx["llm"], requirements, role_context)
            if settings.rag_query_expansion and jd_has_requirements
            else {}
        )

        if probes:
            variants = {req: [queries[req], *probes.get(req, [])] for req in requirements}
            retrieved = _retrieve_with_query_variants(
                embeddings, chunks, variants, top_k=_RETRIEVAL_TOP_K, doc_embeddings=chunk_embeddings
            )
            retrieved = _ensure_section_evidence(retrieved, chunks, state.get("chunk_sections") or [])
            evidence = [
                RetrievedEvidence(requirement=req, evidence=retrieved.get(req, []))
                for req in requirements
            ]
        else:
            retrieved = _retrieve_evidence_for_requirements(
                embeddings,
                chunks,
                list(queries.values()),
                top_k=_RETRIEVAL_TOP_K,
                doc_embeddings=chunk_embeddings,
            )
            by_requirement = _ensure_section_evidence(
                {req: retrieved.get(query, []) for req, query in queries.items()},
                chunks,
                state.get("chunk_sections") or [],
            )
            evidence = [RetrievedEvidence(requirement=req, evidence=by_requirement[req]) for req in requirements]

        return {
            "requirements": requirements,
            "jd_has_requirements": jd_has_requirements,
            "evidence": [e.model_dump() for e in evidence],
            "chunk_embeddings": chunk_embeddings,
            "expanded_queries": bool(probes),
            "path": ["context_routing"],
        }


class ScoringAgent(SubAgent):
    """Writes the assessment, and a verdict per requirement, from the
    retrieved pairs only.

    Sees only requirement-to-evidence pairs: never the full resume, the
    full JD, or the arithmetic score (its verdicts are the other half of
    the match score and must not echo it). Enforced by what the node is
    given, not by instruction.

    On a Clarify retry it also gets the Critic's objections and wider
    evidence, and drops what it cannot support; the Critic runs again."""

    name = "scoring"
    label = "Scoring & Evaluation Agent"
    duty = "Judges each requirement and writes strengths, gaps and summary from the retrieved evidence."

    def run(self, state: Mapping[str, Any], ctx: Mapping[str, Any]) -> dict[str, Any]:
        """Reads `evidence` (and `unsupported_claims` on a rewrite); returns
        the `analysis` with one requirement check per requirement. A model
        failure raises AIExtractionFailedError."""
        from app.services.skill_matching import _ANALYSIS_SYSTEM_PROMPT, _role_context

        requisition = ctx["requisition"]
        evidence = [RetrievedEvidence(**e) for e in state.get("evidence", [])]

        retrieved_block = "\n".join(
            f"- Requirement: {pair.requirement}\n"
            f"  Evidence: {'; '.join(pair.evidence) if pair.evidence else '(no supporting evidence found in the resume)'}"
            for pair in evidence
        )
        # the role, not only its title: whether a qualification is
        # equivalent to the one asked for depends on what the work is
        user_content = (
            f"{_role_context(requisition)}\n\n"
            f"Retrieved requirement-to-evidence pairs — base your analysis "
            f"only on these, not on anything outside them:\n{retrieved_block}"
        )

        # present only on a retry -- the Critic rejected the previous draft
        objections: list[str] = state.get("unsupported_claims") or []
        if objections:
            user_content += (
                "\n\nA reviewer rejected your previous draft. These claims were "
                "not supported by any retrieved evidence:\n"
                + "\n".join(f"- {claim}" for claim in objections)
                + "\n\nRewrite the analysis without them. Do not restate a rejected "
                "claim in softer words — drop it, or replace it with something the "
                "evidence above actually shows. Evidence has been widened since "
                "your last draft, so some gaps may now be answerable."
            )

        analysis = _invoke_structured(
            ctx["llm"],
            SkillMatchAnalysis,
            [
                {"role": "system", "content": _ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        )
        return {"analysis": analysis.model_dump(), "path": ["scoring"]}


_AUDIT_SYSTEM_PROMPT = (
    "You are a compliance reviewer auditing another model's candidate "
    "assessment. You are NOT assessing the candidate and must not offer "
    "your own opinion of their fit. You are given the retrieved evidence "
    "the assessment was supposed to be based on, and the assessment "
    "itself. Your only question is whether each claim in the assessment "
    "traces to that evidence. Set `is_grounded` false and list the exact "
    "offending sentence in `unsupported_claims` when the assessment "
    "asserts experience, credentials, seniority or skills the evidence "
    "does not show, infers a conclusion the evidence does not support, or "
    "states a gap for a requirement whose evidence in fact addresses it. "
    "The same applies to the requirement verdicts: object, quoting the "
    "verdict line, to a `met` or `partial` the quoted evidence does not "
    "support, or a `not_met` for a requirement the evidence clearly "
    "satisfies. "
    "List in `needs_more_context` any requirement whose evidence is too "
    "thin to judge either way. A correctly cautious assessment is "
    "grounded — do not manufacture objections. Evidence text may contain "
    "[REDACTED] or [YEAR] placeholders; that is intentional blinding, "
    "never an error to report."
)


class AuditAgent(SubAgent):
    """The Critic: checks the Scoring Agent's prose against the evidence it
    was given, catching conclusions the evidence does not support.

    A separate model call, because a model checking its own claims in the
    same pass rates them as supported. Returns a verdict only; routing is
    rag_dfa.after_audit's."""

    name = "audit"
    label = "Critic / Guardrail Agent"
    duty = "Audits the assessment for claims the retrieved evidence does not support."

    def run(self, state: Mapping[str, Any], ctx: Mapping[str, Any]) -> dict[str, Any]:
        """Reads `analysis` and `evidence`; returns the Critic's `verdict` and
        the `unsupported_claims` it named. A model failure raises
        AIExtractionFailedError."""
        evidence = [RetrievedEvidence(**e) for e in state.get("evidence", [])]
        analysis = SkillMatchAnalysis(**state["analysis"])

        evidence_block = "\n".join(
            f"- Requirement: {pair.requirement}\n"
            f"  Evidence: {'; '.join(pair.evidence) if pair.evidence else '(none retrieved)'}"
            for pair in evidence
        )
        assessment_block = (
            "Strengths:\n"
            + "\n".join(f"- {s}" for s in analysis.strengths)
            + "\n\nGaps:\n"
            + "\n".join(f"- {g}" for g in analysis.gaps)
            + f"\n\nSummary:\n{analysis.summary}"
            + "\n\nRequirement verdicts:\n"
            + "\n".join(
                f"- [{check.verdict}] {check.requirement} — quoted evidence: "
                f"{check.evidence_quote or '(none)'}"
                for check in analysis.requirement_checks
            )
        )
        verdict = _invoke_structured(
            ctx["llm"],
            AuditVerdict,
            [
                {"role": "system", "content": _AUDIT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"RETRIEVED EVIDENCE:\n{evidence_block}\n\n"
                        f"ASSESSMENT UNDER REVIEW:\n{assessment_block}"
                    ),
                },
            ],
        )
        return {
            "verdict": verdict.model_dump(),
            "unsupported_claims": verdict.unsupported_claims,
            "path": ["audit"],
        }


class ClarifyAgent(SubAgent):
    """Answers a rejected audit by retrieving more for the requirements
    the Critic named (all, if none), then sends the draft back.

    With query expansion off it widens k on the same query; with it on it
    also asks for *different* probes, told what the Critic could not
    support.

    Increments `clarify_loops` *before* routing, so rag_dfa.after_clarify
    reads the attempt just made; that counter is what bounds the cycle.
    The visit that exhausts the budget retrieves nothing."""

    name = "clarify"
    label = "Clarify Agent"
    duty = "Widens retrieval on the Critic's objections and requests a rewrite."

    def run(self, state: Mapping[str, Any], ctx: Mapping[str, Any]) -> dict[str, Any]:
        """Reads the Critic's `verdict` and the retrieval state; returns the
        incremented `clarify_loops` and, while budget remains, wider
        `evidence` for the requirements it named (all, if it named none).
        On the visit that exhausts the budget it retrieves nothing
        (after_clarify decides)."""
        from app.domain.rag_dfa import after_clarify
        from app.services.skill_matching import (
            _ensure_section_evidence,
            _retrieve_evidence_for_requirements,
            _retrieve_with_query_variants,
            _RETRIEVAL_TOP_K,
        )

        verdict = AuditVerdict(**state["verdict"])
        requirements: list[str] = state.get("requirements") or []
        chunks: list[str] = state.get("redacted_chunks") or []
        loops = state.get("clarify_loops", 0) + 1

        if after_clarify(clarify_loops=loops) == "manual_review":
            _log.info("Clarify budget exhausted after %s rewrite(s); routing to manual review", loops - 1)
            return {"clarify_loops": loops, "path": ["clarify"]}

        # the Critic names requirements it could not judge; when it names
        # none, the objection was about the prose, so re-query everything
        focus = [req for req in requirements if req in set(verdict.needs_more_context)] or requirements

        requisition = ctx["requisition"]
        role_context = f"{requisition.title}, {requisition.department}"
        queries = {req: f"{req} (for the role: {role_context})" for req in focus}

        widened_k = _RETRIEVAL_TOP_K + _CLARIFY_K_BONUS * loops
        doc_embeddings = state.get("chunk_embeddings") or None

        probes = (
            _expand_queries(ctx["llm"], focus, role_context, objections=verdict)
            if settings.rag_query_expansion
            else {}
        )

        if probes:
            variants = {req: [queries[req], *probes.get(req, [])] for req in focus}
            retrieved_by_requirement = _retrieve_with_query_variants(
                ctx["embeddings"], chunks, variants, top_k=widened_k, doc_embeddings=doc_embeddings
            )
        else:
            by_query = _retrieve_evidence_for_requirements(
                ctx["embeddings"],
                chunks,
                list(queries.values()),
                top_k=widened_k,
                doc_embeddings=doc_embeddings,
            )
            retrieved_by_requirement = {req: by_query.get(query, []) for req, query in queries.items()}
        retrieved_by_requirement = _ensure_section_evidence(
            retrieved_by_requirement, chunks, state.get("chunk_sections") or []
        )

        # merge rather than replace: requirements the Critic was satisfied
        # with keep the evidence that satisfied it
        widened = {req: pair for req, pair in ((e["requirement"], e) for e in state.get("evidence", []))}
        for req in focus:
            widened[req] = {"requirement": req, "evidence": retrieved_by_requirement.get(req, [])}

        _log.info(
            "Clarify retry %s/%s: %s requirement(s) re-queried at k=%s (%s)",
            loops,
            MAX_CLARIFY_LOOPS,
            len(focus),
            widened_k,
            "reformulated probes" if probes else "same query, wider k",
        )
        return {
            "evidence": [widened[req] for req in requirements if req in widened],
            "clarify_loops": loops,
            "path": ["clarify"],
        }


def _verdict_block(
    checks: list[RequirementCheck],
    evidence_by_requirement: Mapping[str, list[str]],
    notes: Mapping[str, str] | None = None,
    role: str = "",
) -> str:
    """The verdicts as the two verdict agents read them, headed by the
    role they are judged for -- the same evidence can meet a requirement
    for one role and only partly meet it for another."""
    lines = [f"The role:\n{role}"] if role else []
    for index, check in enumerate(checks, 1):
        evidence = evidence_by_requirement.get(check.requirement) or []
        block = (
            f"Requirement {index}: {check.requirement}\n"
            f"Evidence retrieved for it: {'; '.join(evidence) if evidence else '(none retrieved)'}\n"
            f"Verdict: {check.verdict} (basis: {check.basis})\n"
            f"Quoted evidence: {check.evidence_quote or '(none)'}"
        )
        if check.reasoning:
            block += f"\nReasoning given: {check.reasoning}"
        if notes and notes.get(check.requirement):
            block += f"\nWhy it is being looked at again: {notes[check.requirement]}"
        lines.append(block)
    return "\n\n".join(lines)


_VERDICT_AUDIT_SYSTEM_PROMPT = (
    "You audit another model's per-requirement verdicts on a job candidate. "
    "For each requirement you are given the evidence retrieved from the "
    "candidate's résumé, the verdict (met, partial or not_met) and the "
    "evidence it quoted. Judge each verdict on its own, against that "
    "requirement's evidence only. Object when a met or partial verdict is "
    "not borne out by the evidence, and — just as important — when a "
    "not_met verdict is wrong because the evidence does satisfy the "
    "requirement, including through an equivalent qualification the "
    "first verdict read too literally, and when an `equivalent` basis "
    "is claimed for something that is only similar. Copy the requirement text exactly into `requirement` and "
    "say in one sentence what is wrong. Do not object to a verdict you "
    "agree with, and do not object only because you would word it "
    "differently. Evidence may contain [REDACTED] or [YEAR] placeholders; "
    "that is intentional blinding, never an error.\n\n"
)


class VerdictAuditAgent(SubAgent):
    """Audits the requirement verdicts one by one, each beside its own
    evidence, apart from the prose, so one bad verdict is an objection to
    that verdict alone.

    Runs after the automaton halts and routes nothing, so it is not in
    RAG_AGENTS or rag_dfa.TRANSITIONS (rag_pipeline._settle_verdicts calls
    it)."""

    name = "verdict_audit"
    label = "Verdict Auditor"
    duty = "Audits each requirement verdict on its own, against that requirement's evidence."

    def run(self, state: Mapping[str, Any], ctx: Mapping[str, Any]) -> dict[str, Any]:
        from app.services.skill_matching import _REQUIREMENT_READING_RULE, _role_context

        checks = [RequirementCheck(**c) for c in state["checks"]]
        role = _role_context(ctx.get("requisition"))
        result = _invoke_structured(
            ctx["llm"],
            VerdictAuditResult,
            [
                {"role": "system", "content": _VERDICT_AUDIT_SYSTEM_PROMPT + _REQUIREMENT_READING_RULE},
                {"role": "user", "content": _verdict_block(checks, state["evidence_by_requirement"], role=role)},
            ],
        )
        known = {check.requirement for check in checks}
        return {
            "objections": {o.requirement: o.objection for o in result.objections if o.requirement in known}
        }


_RECHECK_SYSTEM_PROMPT = (
    "You take a second, careful look at verdicts on a job candidate that "
    "were disputed. For each requirement you are given the whole of the "
    "candidate's résumé (blinded), the first verdict, its quoted evidence, "
    "and why it is being looked at again. Decide the verdict "
    "afresh — met, partial or not_met — from that evidence alone. Copy the "
    "requirement text exactly into `requirement`. `evidence_quote` must be "
    "the exact words, copied verbatim from ONE evidence item for that "
    "requirement, that your verdict rests on; a not_met needs none. Set "
    "`basis` and `reasoning` as the first verdict was asked to. Being "
    "asked again is not a hint that the first verdict was wrong: keep it "
    "when the evidence supports it.\n\n"
)


class VerdictRecheckAgent(SubAgent):
    """A second look at the verdicts that were disputed -- by the Verdict
    Auditor, or by the numbers: a not_met for a requirement the resume
    matched strongly on the arithmetic half (see rag_pipeline.
    _CONTRADICTION_SEMANTIC). One model call for all of them, and its
    answers go through the same quote check as the first verdicts.

    Same standing as VerdictAuditAgent: after the automaton, not in it."""

    name = "verdict_recheck"
    label = "Verdict Re-check Agent"
    duty = "Re-judges disputed requirement verdicts from their evidence."

    def run(self, state: Mapping[str, Any], ctx: Mapping[str, Any]) -> dict[str, Any]:
        from app.services.skill_matching import _REQUIREMENT_READING_RULE, _role_context

        checks = [RequirementCheck(**c) for c in state["checks"]]
        role = _role_context(ctx.get("requisition"))
        result = _invoke_structured(
            ctx["llm"],
            RecheckResult,
            [
                {"role": "system", "content": _RECHECK_SYSTEM_PROMPT + _REQUIREMENT_READING_RULE},
                {
                    "role": "user",
                    "content": _verdict_block(checks, state["evidence_by_requirement"], state["reasons"], role=role),
                },
            ],
        )
        wanted = {check.requirement for check in checks}
        return {"rechecked": [c for c in result.requirement_checks if c.requirement in wanted]}


INGESTION = IngestionAgent()
VALIDATION = ValidationAgent()
COMPLIANCE = ComplianceAgent()
CONTEXT_ROUTING = ContextRouterAgent()
SCORING = ScoringAgent()
AUDIT = AuditAgent()
CLARIFY = ClarifyAgent()
VERDICT_AUDIT = VerdictAuditAgent()
VERDICT_RECHECK = VerdictRecheckAgent()

#: In the automaton's happy-path order. Each has one checkable duty, and
#: returns facts; routing is rag_dfa.TRANSITIONS. `rejected` and
#: `manual_review` are states, not agents (plain nodes in rag_pipeline.py).
RAG_AGENTS: tuple[SubAgent, ...] = (
    INGESTION,
    VALIDATION,
    COMPLIANCE,
    CONTEXT_ROUTING,
    SCORING,
    AUDIT,
    CLARIFY,
)

RAG_BY_NAME: dict[str, SubAgent] = {agent.name: agent for agent in RAG_AGENTS}

#: Run after the automaton halts, on its verdicts; not states of it
#: (rag_pipeline._settle_verdicts).
VERDICT_AGENTS: tuple[SubAgent, ...] = (VERDICT_AUDIT, VERDICT_RECHECK)
