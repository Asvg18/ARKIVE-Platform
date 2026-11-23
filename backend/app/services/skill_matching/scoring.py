"""The match score's arithmetic: the per-requirement similarity half, the
verified coverage half, and the breakdown HR reads beside the score.
"""

import math

from langchain_openai import OpenAIEmbeddings

from app.domain.insights import MATCH_FLAG_THRESHOLD
from app.schemas.skill_match import MatchBreakdown, RequirementCheck, RequirementScore

from .retrieval import _cosine_similarity, _embed
from .text import _tokenize

# Changing a weight or threshold below is an algorithm change: re-run
# scripts/eval_skill_matching.py.
# slightly favors semantic over keyword -- catches conceptual matches
# BM25 can't (e.g. "built LLM-backed tools" satisfying "AI/ML experience")
_SEMANTIC_WEIGHT = 0.6
# Raw cosine is not a percentage: even an excellent resume/job pair sits
# far from 1.0. These anchors stretch the measured span onto 0-100,
# clamped. They were measured on whole documents, not requirement/unit
# pairs; re-measure before quoting a score band (see the algorithm doc).
# Migration f7d2a9c4e815 keeps its own copy, so a change here only
# affects new scores.
_SEMANTIC_COSINE_FLOOR = 0.20
_SEMANTIC_COSINE_CEILING = 0.70
_COVERAGE_WEIGHT = 0.5
_VERDICT_POINTS = {"met": 1.0, "partial": 0.5, "not_met": 0.0}
# below this an application is flagged instead of advanced; shared with
# insights.py, which describes the threshold to HR
_FLAG_THRESHOLD = MATCH_FLAG_THRESHOLD


def _semantic_score(cosine: float) -> float:
    """Cosine similarity mapped onto 0-100 between the calibration
    anchors, clamped at both ends."""
    span = _SEMANTIC_COSINE_CEILING - _SEMANTIC_COSINE_FLOOR
    return max(0.0, min(100.0, (cosine - _SEMANTIC_COSINE_FLOOR) / span * 100))


def _bm25_keyword_scores(query_text: str, corpus_texts: list[str]) -> list[float]:
    from rank_bm25 import BM25Okapi

    tokenized_corpus = [_tokenize(t) for t in corpus_texts]
    bm25 = BM25Okapi(tokenized_corpus)
    raw_scores = bm25.get_scores(_tokenize(query_text))

    lo, hi = min(raw_scores), max(raw_scores)
    if hi - lo < 1e-9:
        # no signal to divide by (one job, or no overlap): neutral 50
        return [50.0 for _ in raw_scores]
    return [(s - lo) / (hi - lo) * 100 for s in raw_scores]


_BM25_K1 = 1.5
_BM25_B = 0.75


def _bm25_scores(query: list[str], corpus: list[list[str]]) -> list[float]:
    """BM25 of one tokenised query against every document of `corpus`,
    with Lucene's idf, log(1 + (N - n + 0.5) / (n + 0.5)), which stays
    positive however common a word is. Otherwise the same formula, and
    the same k1 and b, as rank_bm25's BM25Okapi."""
    doc_count = len(corpus)
    average_length = sum(len(doc) for doc in corpus) / doc_count or 1.0
    frequency = {token: sum(1 for doc in corpus if token in doc) for token in set(query)}
    idf = {
        token: math.log(1 + (doc_count - n + 0.5) / (n + 0.5)) for token, n in frequency.items()
    }
    scores = []
    for doc in corpus:
        norm = _BM25_K1 * (1 - _BM25_B + _BM25_B * len(doc) / average_length)
        score = 0.0
        for token in query:
            f = doc.count(token)
            if f:
                score += idf[token] * f * (_BM25_K1 + 1) / (f + norm)
        scores.append(score)
    return scores


def _keyword_scores_per_requirement(requirements: list[str], units: list[str]) -> list[float]:
    """BM25 of each requirement against the resume units, as a share of
    the best score that requirement could get -- 0-100 without needing a
    second job to compare with.

    "The best it could get" is the requirement scored against itself,
    with the requirement lines added to the corpus so it has an idf to be
    scored by. That is what puts a 3-unit resume and a 30-unit one on the
    same scale. If BM25 has no signal at all (a tiny or degenerate
    corpus), the share of the requirement's words found in the resume
    stands in.

    Uses _bm25_scores, not BM25Okapi: Okapi's idf is zero for a word in
    half the corpus, which here is every word a short resume shares with
    the requirement, so the closer the match the lower the score."""
    unit_docs = [_tokenize(unit) for unit in units]
    requirement_docs = [_tokenize(requirement) for requirement in requirements]
    resume_vocab = {token for doc in unit_docs for token in doc}
    corpus = unit_docs + requirement_docs
    has_corpus = any(corpus)

    scores: list[float] = []
    for index, query in enumerate(requirement_docs):
        if not query or not resume_vocab:
            scores.append(0.0)
            continue
        share = None
        if has_corpus:
            raw = _bm25_scores(query, corpus)
            best = max(raw[: len(unit_docs)])
            ceiling = raw[len(unit_docs) + index]
            if ceiling > 1e-9:
                share = max(0.0, min(1.0, best / ceiling))
        if share is None:
            words = set(query)
            share = len(words & resume_vocab) / len(words)
        scores.append(share * 100)
    return scores


def _score_requirements(
    embeddings: OpenAIEmbeddings, requirements: list[str], units: list[str]
) -> list[tuple[float, float, float, str]]:
    """The arithmetic half, per requirement of the applied-to job: returns
    (semantic, keyword, best cosine, closest unit) for each.

    semantic = the best cosine between the requirement and any resume unit,
    calibrated onto 0-100 (_semantic_score); keyword = BM25 share of the
    requirement's own best score (_keyword_scores_per_requirement). The
    closest unit is kept so HR can see which resume line the similarity
    came from. One embeddings call covers every requirement and unit."""
    if not units:
        return [(0.0, 0.0, 0.0, "") for _ in requirements]
    vectors = _embed(embeddings, requirements + units)
    requirement_vectors, unit_vectors = vectors[: len(requirements)], vectors[len(requirements) :]
    keyword = _keyword_scores_per_requirement(requirements, units)
    results = []
    for vector, keyword_score in zip(requirement_vectors, keyword):
        cosines = [_cosine_similarity(vector, unit) for unit in unit_vectors]
        best = max(range(len(cosines)), key=cosines.__getitem__)
        results.append((_semantic_score(cosines[best]), keyword_score, cosines[best], units[best]))
    return results


def _requirement_scores(
    requirements: list[str],
    per_requirement: list[tuple[float | None, float | None, float | None, str]],
    checks: list[RequirementCheck],
) -> list[RequirementScore]:
    """Both halves of the score, one row per requirement -- what HR is
    shown as the rubric. Rows line up with the checks by requirement
    text; a requirement with no check (the Critic produced none) earns
    no coverage points, which is also how _requirement_coverage counts
    it."""
    by_requirement = {check.requirement: check for check in checks}
    rows: list[RequirementScore] = []
    for requirement, (semantic, keyword, _, closest) in zip(requirements, per_requirement):
        check = by_requirement.get(requirement)
        points = _VERDICT_POINTS[check.verdict] if check is not None and check.verified else 0.0
        # None when rebuilt from a v2 payload (read_match_breakdown)
        measured = semantic is not None and keyword is not None
        rows.append(
            RequirementScore(
                requirement=requirement,
                semantic_score=round(semantic, 1) if measured else None,
                keyword_score=round(keyword, 1) if measured else None,
                similarity_score=(
                    round(_SEMANTIC_WEIGHT * semantic + (1 - _SEMANTIC_WEIGHT) * keyword, 1) if measured else None
                ),
                closest_resume_text=closest,
                **(
                    {}
                    if check is None
                    else {
                        "verdict": check.verdict,
                        "basis": check.basis,
                        "reasoning": check.reasoning,
                        "evidence_quote": check.evidence_quote,
                        "verified": check.verified,
                        "note": check.note,
                    }
                ),
                points=points,
            )
        )
    return rows


def _requirement_coverage(checks: list[RequirementCheck]) -> float:
    """The coverage half: the verified share of requirements met, 0-100.

    Each check scores _VERDICT_POINTS (met 1, partial 0.5, not_met 0), and
    a check whose quote did not hold up (verified False) scores 0. Checks
    arrive one per requirement (rag_pipeline aligns them), so a skipped
    requirement is already a not_met here."""
    if not checks:
        return 0.0
    points = [_VERDICT_POINTS[check.verdict] if check.verified else 0.0 for check in checks]
    return sum(points) / len(points) * 100


def read_match_breakdown(payload: dict | None) -> MatchBreakdown | None:
    """The rubric behind a stored skill-matching result, for HR.

    Reads only what was stored, so a score is explained as it was
    computed. Older payloads have less: some carry verdicts without each
    requirement's similarity, and the oldest only the two whole-resume
    figures, with no rows."""
    if not payload or payload.get("match_score") is None:
        return None
    # field by field rather than SkillMatchResult.model_validate: older
    # and hand-seeded payloads carry the score without the rest
    rows = [RequirementScore.model_validate(row) for row in payload.get("requirement_scores") or []]
    checks = [RequirementCheck.model_validate(check) for check in payload.get("requirement_checks") or []]
    if not rows and checks:
        rows = _requirement_scores(
            [check.requirement for check in checks], [(None, None, None, "")] * len(checks), checks
        )
    return MatchBreakdown(
        score_method=payload.get("score_method") or "",
        match_score=payload["match_score"],
        arithmetic_score=payload.get("arithmetic_score"),
        semantic_score=payload.get("semantic_score"),
        keyword_score=payload.get("keyword_score"),
        requirement_coverage=payload.get("requirement_coverage"),
        semantic_weight=_SEMANTIC_WEIGHT,
        coverage_weight=_COVERAGE_WEIGHT,
        verdict_points=dict(_VERDICT_POINTS),
        flag_threshold=_FLAG_THRESHOLD,
        requirements=rows,
    )


def _mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0
