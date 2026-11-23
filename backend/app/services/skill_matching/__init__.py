"""The Skill Matching Agent: scores a resume against the job it was
submitted for (run_skill_matching) and explains the score. Full algorithm
and measurements: docs/ARKIVE-skill-matching-algorithm.md.

The steps live in text, evidence, retrieval, scoring and prompts; this
module runs them, holds the model clients and the embedding cache, and
ranks other openings. Their names are re-exported here, so
`skill_matching.<name>` keeps working for every caller.
"""

import logging
from datetime import date

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.infra.config import settings
# the retrieval automaton's dead ends -- reaching either means the
# assessment below was never verified (shown to HR, but not a flag)
from app.domain.rag_dfa import TERMINAL as UNVERIFIED_TERMINAL_STATES
from app.models.application_resume import ApplicationResume
from app.models.candidate_application import CandidateApplication
from app.models.enums import RequisitionStatus
from app.models.job_requisition import JobRequisition
from app.schemas.skill_match import RAGTrace, RequisitionMatch, SkillMatchAnalysis, SkillMatchResult
from app.services.agents import SKILL_MATCHING
from app.services.job_descriptions import current_version_number
from app.services.pdf_text import AIExtractionFailedError, ExtractionNotConfiguredError

# Names not used below are re-exported: tests, scripts and the RAG agents
# read them as skill_matching.<name>.
from .evidence import (  # noqa: F401
    _CREDENTIAL_REQUIREMENT_RE,
    _CREDENTIAL_SECTION_RE,
    _EDUCATION_REQUIREMENT_RE,
    _SECTION_EVIDENCE_LIMIT,
    _chunk_jd_requirements,
    _chunk_resume_evidence,
    _ensure_section_evidence,
    _fallback_resume_chunks,
    _labelled_resume_evidence,
    _requirement_sections,
    _resume_units,
    _role_context,
    _target_requirements,
)
from .prompts import _ANALYSIS_SYSTEM_PROMPT, _REQUIREMENT_READING_RULE  # noqa: F401
from .retrieval import (  # noqa: F401
    _EMBEDDING_MODEL,
    _RETRIEVAL_TOP_K,
    _EmbeddingSimilarityRetriever,
    _cosine_similarity,
    _embed,
    _ensemble_rank,
    _fuse_rankings,
    _retrieve_evidence_for_requirements,
    _retrieve_with_query_variants,
)
from .scoring import (  # noqa: F401
    _BM25_B,
    _BM25_K1,
    _COVERAGE_WEIGHT,
    _FLAG_THRESHOLD,
    _SEMANTIC_COSINE_CEILING,
    _SEMANTIC_COSINE_FLOOR,
    _SEMANTIC_WEIGHT,
    _VERDICT_POINTS,
    _bm25_keyword_scores,
    _bm25_scores,
    _keyword_scores_per_requirement,
    _mean,
    _requirement_coverage,
    _requirement_scores,
    _score_requirements,
    _semantic_score,
    read_match_breakdown,
)
from .text import (  # noqa: F401
    _BULLET_PREFIX_RE,
    _DEGREE_FORMS,
    _POSSESSIVE_RE,
    _requisition_corpus_text,
    _resume_scoring_text,
    _stem,
    _tokenize,
)

__all__ = [
    "AIExtractionFailedError",
    "ExtractionNotConfiguredError",
    "live_suggestions",
    "read_match_breakdown",
    "run_skill_matching",
    "warm_up",
]


_log = logging.getLogger(__name__)

SCORE_METHOD = "applied_job_v4"
_SUGGESTION_LIMIT = 3


def _get_or_compute_requisition_embedding(
    embeddings: OpenAIEmbeddings, requisition: JobRequisition
) -> list[float]:
    if requisition.embedding is not None:
        return requisition.embedding
    embedding = _embed(embeddings, [_requisition_corpus_text(requisition)])[0]
    requisition.embedding = embedding
    return embedding


def _get_or_compute_resume_embedding(
    embeddings: OpenAIEmbeddings, resume: ApplicationResume
) -> list[float]:
    # safe to cache: the form is written once, at upload, never edited
    if resume.embedding is not None:
        return resume.embedding
    embedding = _embed(embeddings, [_resume_scoring_text(resume)])[0]
    resume.embedding = embedding
    return embedding


def _real_top_skills(resume: ApplicationResume, target_corpus_text: str) -> list[str]:
    """Which of the candidate's own extracted skills actually show up in
    this job's requirements text -- evidence of fit, not a random sample.
    Falls back to the full skills list if none happen to overlap."""
    corpus_lower = target_corpus_text.lower()
    overlap = [s for s in resume.skills if s.lower() in corpus_lower]
    return (overlap or list(resume.skills))[:5]


def _generate_analysis(
    llm: ChatOpenAI,
    embeddings: OpenAIEmbeddings,
    resume: ApplicationResume,
    requisition: JobRequisition,
    combined_score: float,
    requirement_signals: dict[str, float] | None = None,
) -> tuple[SkillMatchAnalysis, RAGTrace]:
    """The qualitative half, delegated to the retrieval sub-graph.

    `requirement_signals` is each requirement's semantic score from the
    arithmetic half. The verdict settlement uses it to catch a not_met
    the numbers contradict -- it is never shown to a model.

    The sub-graph is imported inside the function: its agents import this
    module back for the shared retrieval primitives, so a top-level import
    would be circular.
    """
    from app.services.rag_pipeline import run_rag_analysis

    return run_rag_analysis(
        llm=llm,
        embeddings=embeddings,
        resume=resume,
        requisition=requisition,
        combined_score=combined_score,
        requirement_signals=requirement_signals,
    )


# One client per process, not per request: each construction opens its
# own connection pool, so per-request clients pay a fresh TLS handshake
# every time.
_embeddings_client: OpenAIEmbeddings | None = None
_llm_client: ChatOpenAI | None = None


def _get_embeddings() -> OpenAIEmbeddings:
    global _embeddings_client
    if _embeddings_client is None:
        _embeddings_client = OpenAIEmbeddings(model=_EMBEDDING_MODEL, api_key=settings.openai_api_key)
    return _embeddings_client


def _get_llm() -> ChatOpenAI:
    global _llm_client
    if _llm_client is None:
        # temperature 0: its verdicts are half of the match score, which
        # must not move between two runs on the same resume
        _llm_client = ChatOpenAI(model="gpt-4o-mini", api_key=settings.openai_api_key, temperature=0)
    return _llm_client


def warm_up() -> None:
    """Opens the model connections at server startup instead of on the
    first submission. Never raises: a failure must not stop the server
    starting."""
    if not settings.openai_api_key:
        return
    try:
        _get_embeddings().embed_query("warm-up")
        _get_llm().invoke("Reply with OK.")
    except Exception:
        pass


def _open_for_applications():
    """The same "open" the public job board and POST /applications use:
    published and not past its deadline (status alone stays `open` after
    the deadline)."""
    return (
        JobRequisition.status == RequisitionStatus.open,
        or_(JobRequisition.application_deadline.is_(None), JobRequisition.application_deadline >= date.today()),
    )


def _applied_requisition_ids(db: Session, applicant_id: int | None, requisition_ids=None) -> set[int]:
    """Every job this applicant has applied to, whatever became of it;
    those are never suggested."""
    if applicant_id is None:
        return set()
    query = select(CandidateApplication.requisition_id).where(CandidateApplication.applicant_id == applicant_id)
    if requisition_ids is not None:
        query = query.where(CandidateApplication.requisition_id.in_(requisition_ids))
    return set(db.scalars(query))


def live_suggestions(db: Session, *, applicant_id: int, suggestions: list[dict]) -> list[dict]:
    """Stored suggestions minus any no longer true: the job closed or
    passed its deadline, or the applicant has since applied. Run on every
    read, since the stored list is frozen at scoring time."""
    ids = [s["requisition_id"] for s in suggestions]
    if not ids:
        return []
    still_open = set(db.scalars(select(JobRequisition.id).where(JobRequisition.id.in_(ids), *_open_for_applications())))
    available = still_open - _applied_requisition_ids(db, applicant_id, ids)
    return [s for s in suggestions if s["requisition_id"] in available]


def _suggest_other_openings(
    db: Session, embeddings: OpenAIEmbeddings, resume: ApplicationResume, target_requisition: JobRequisition
) -> list[RequisitionMatch]:
    """Other open jobs a below-threshold candidate may fit better.

    Deliberately not the match score's method, and never fed back into
    it: one whole-resume pass against every open job (calibrated cosine +
    BM25 normalised across those jobs), which is cheap enough to run over
    all of them, where the per-requirement score would cost a model call
    per job. Openings scoring at least the threshold on this ranking are
    suggested, best first.

    Only jobs still taking applications that this applicant has not
    applied to are considered."""
    applicant_id = db.scalar(
        select(CandidateApplication.applicant_id).where(CandidateApplication.id == resume.application_id)
    )
    excluded = _applied_requisition_ids(db, applicant_id) | {target_requisition.id}
    others = [
        r
        for r in db.scalars(select(JobRequisition).where(*_open_for_applications()))
        if r.id not in excluded
    ]
    if not others:
        return []
    resume_embedding = _get_or_compute_resume_embedding(embeddings, resume)
    keyword_scores = _bm25_keyword_scores(
        _resume_scoring_text(resume), [_requisition_corpus_text(r) for r in others]
    )
    ranked: list[RequisitionMatch] = []
    for requisition, keyword_score in zip(others, keyword_scores):
        cosine = _cosine_similarity(resume_embedding, _get_or_compute_requisition_embedding(embeddings, requisition))
        semantic_score = _semantic_score(cosine)
        combined_score = _SEMANTIC_WEIGHT * semantic_score + (1 - _SEMANTIC_WEIGHT) * keyword_score
        ranked.append(
            RequisitionMatch(
                requisition_id=requisition.id,
                title=requisition.title,
                department=requisition.department,
                semantic_score=round(semantic_score, 1),
                keyword_score=round(keyword_score, 1),
                combined_score=round(combined_score, 1),
                cosine_similarity=round(cosine, 4),
            )
        )
    ranked.sort(key=lambda m: m.combined_score, reverse=True)
    return [m for m in ranked if m.combined_score >= _FLAG_THRESHOLD][:_SUGGESTION_LIMIT]


def run_skill_matching(
    db: Session, *, resume: ApplicationResume, target_requisition: JobRequisition
) -> SkillMatchResult:
    """Score `resume` against `target_requisition` and explain the score.

        match = 0.5 x arithmetic + 0.5 x coverage      (_COVERAGE_WEIGHT)

    1. Arithmetic half, no model: for each requirement of the applied-to
       job, 0.6 x semantic + 0.4 x keyword (_SEMANTIC_WEIGHT), averaged
       over the requirements (_score_requirements).
    2. Coverage half: the retrieval graph writes a verdict per requirement
       from retrieved evidence, and the verdicts are quote-checked,
       audited and re-checked (_generate_analysis,
       rag_pipeline._settle_verdicts); _requirement_coverage scores them.
       With no verdicts at all, the match is the arithmetic half alone.
    3. Below MATCH_FLAG_THRESHOLD the application is flagged and other open
       jobs are suggested (_suggest_other_openings, never part of the
       score).

    Records an agent run on `db` without committing. Raises
    ExtractionNotConfiguredError without an OpenAI key; a model failure
    propagates as AIExtractionFailedError.
    """
    if not settings.openai_api_key:
        _log.error(
            "AI skill matching is unavailable: OPENAI_API_KEY is not set. "
            "See backend/.env.example."
        )
        raise ExtractionNotConfiguredError(
            "Pre-screening is temporarily unavailable, so your answers were not "
            "submitted. Please try again shortly. If it keeps happening, contact "
            "the HR office."
        )

    embeddings = _get_embeddings()
    llm = _get_llm()

    # step 1: only the applied-to job's requirements, never other jobs
    requirements, _ = _target_requirements(target_requisition)
    per_requirement = _score_requirements(embeddings, requirements, _resume_units(resume))
    semantic_score = _mean(s for s, _, _, _ in per_requirement)
    keyword_score = _mean(k for _, k, _, _ in per_requirement)
    cosine = _mean(c for _, _, c, _ in per_requirement)
    arithmetic_score = _mean(
        _SEMANTIC_WEIGHT * s + (1 - _SEMANTIC_WEIGHT) * k for s, k, _, _ in per_requirement
    )

    # step 2: the model is never shown the arithmetic score; the semantic
    # scores only decide which verdicts are re-checked
    signals = {requirement: s for requirement, (s, _, _, _) in zip(requirements, per_requirement)}
    analysis, rag_trace = _generate_analysis(
        llm, embeddings, resume, target_requisition, arithmetic_score, signals
    )
    top_skills = _real_top_skills(resume, _requisition_corpus_text(target_requisition))

    # `unverified`: the Critic never signed off the written assessment. The
    # verdicts are audited separately, so they still count.
    unverified = rag_trace is not None and rag_trace.terminal_state in UNVERIFIED_TERMINAL_STATES
    requirement_coverage = (
        _requirement_coverage(analysis.requirement_checks) if analysis.requirement_checks else None
    )
    if requirement_coverage is None:
        match_score = arithmetic_score
    else:
        match_score = (1 - _COVERAGE_WEIGHT) * arithmetic_score + _COVERAGE_WEIGHT * requirement_coverage

    # step 3: only the score flags. An unverified assessment does not (it
    # is about the assessment, not the candidate); HR sees it marked
    below_threshold = round(match_score, 1) < _FLAG_THRESHOLD
    flagged = below_threshold
    flag_reason = "below_threshold" if below_threshold else ""

    suggestions = (
        _suggest_other_openings(db, embeddings, resume, target_requisition) if below_threshold else []
    )

    result = SkillMatchResult(
        match_score=round(match_score, 1),
        semantic_score=round(semantic_score, 1),
        keyword_score=round(keyword_score, 1),
        cosine_similarity=round(cosine, 4),
        arithmetic_score=round(arithmetic_score, 1),
        requirement_coverage=None if requirement_coverage is None else round(requirement_coverage, 1),
        requirement_checks=analysis.requirement_checks,
        requirement_scores=_requirement_scores(requirements, per_requirement, analysis.requirement_checks),
        score_method=SCORE_METHOD,
        top_skills=top_skills,
        strengths=analysis.strengths,
        gaps=analysis.gaps,
        summary=analysis.summary,
        flagged=flagged,
        flag_reason=flag_reason,
        suggested_requisitions=suggestions,
        rag_trace=rag_trace,
        jd_version=current_version_number(db, target_requisition.id),
    )
    SKILL_MATCHING.log(
        db,
        application_id=resume.application_id,
        triggered_by_stage="skill_matching",
        output=result.model_dump(),
    )
    return result
