"""Hybrid retrieval: embeddings, BM25 and Reciprocal Rank Fusion, finding
each requirement's evidence among the resume's chunks.
"""

import math

import openai
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_openai import OpenAIEmbeddings
from pydantic import Field

from app.services.pdf_text import AIExtractionFailedError

from .text import _tokenize

_EMBEDDING_MODEL = "text-embedding-3-small"
# How many resume evidence chunks to retrieve per JD requirement chunk.
_RETRIEVAL_TOP_K = 3


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _embed(embeddings: OpenAIEmbeddings, texts: list[str]) -> list[list[float]]:
    try:
        return embeddings.embed_documents(texts)
    except openai.OpenAIError as exc:
        raise AIExtractionFailedError(
            "Pre-screening could not be completed, so your answers were not "
            "submitted. Please try again shortly. If it keeps happening, contact "
            "the HR office."
        ) from exc


class _EmbeddingSimilarityRetriever(BaseRetriever):
    """The semantic half of the hybrid retriever -- cosine similarity
    over precomputed chunk embeddings, wrapped as a real BaseRetriever so
    it fuses with BM25Retriever the same way any two LangChain
    retrievers would."""

    docs: list[Document] = Field(repr=False)
    doc_embeddings: list[list[float]] = Field(repr=False)
    embeddings: OpenAIEmbeddings
    k: int = _RETRIEVAL_TOP_K
    model_config = {"arbitrary_types_allowed": True}

    def _get_relevant_documents(self, query: str, **kwargs) -> list[Document]:
        query_embedding = self.embeddings.embed_query(query)
        scored = [
            (doc, _cosine_similarity(query_embedding, doc_embedding))
            for doc, doc_embedding in zip(self.docs, self.doc_embeddings)
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [doc for doc, _ in scored[: self.k]]


def _fuse_rankings(ranked_lists: list[list[Document]], k: int) -> list[Document]:
    """Reciprocal Rank Fusion over any number of ranked lists.
    score(doc) = sum of 1/(60 + rank) across whichever lists it appears
    in; 60 is the standard RRF damping constant.

    N lists for query expansion: RRF needs no comparable scores, and the
    plain requirement is always one of the lists, so bad probes dilute
    rather than displace it."""
    scores: dict[str, float] = {}
    by_content: dict[str, Document] = {}
    for docs in ranked_lists:
        for rank, doc in enumerate(docs):
            scores[doc.page_content] = scores.get(doc.page_content, 0.0) + 1.0 / (60 + rank)
            by_content[doc.page_content] = doc
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [by_content[content] for content, _ in ranked[:k]]


def _ensemble_rank(bm25_docs: list[Document], semantic_docs: list[Document], k: int) -> list[Document]:
    """The two-list case: the keyword half fused with the semantic half.
    Stands in for langchain.retrievers.EnsembleRetriever, which no longer
    exists in current LangChain."""
    return _fuse_rankings([bm25_docs, semantic_docs], k=k)


def _retrieve_evidence_for_requirements(
    embeddings: OpenAIEmbeddings,
    resume_chunks: list[str],
    jd_requirement_chunks: list[str],
    top_k: int = _RETRIEVAL_TOP_K,
    doc_embeddings: list[list[float]] | None = None,
) -> dict[str, list[str]]:
    """For each JD requirement, retrieves the top-k most relevant resume
    chunks via hybrid retrieval. This is the step that makes the analysis
    genuinely retrieval-augmented -- the generator only sees what comes
    back here, never the full resume.

    `doc_embeddings` reuses embeddings already computed for these chunks
    (the Clarify Agent's wider-k retry); omitted, they are computed
    here."""
    if not resume_chunks:
        return {requirement: [] for requirement in jd_requirement_chunks}

    k = min(top_k, len(resume_chunks))
    docs = [Document(page_content=chunk) for chunk in resume_chunks]
    bm25_retriever = BM25Retriever.from_documents(docs, k=k, preprocess_func=_tokenize)
    # length mismatch means they aren't embeddings of these chunks --
    # ignore them rather than zip-truncating into silently wrong rankings
    if doc_embeddings is None or len(doc_embeddings) != len(resume_chunks):
        doc_embeddings = _embed(embeddings, resume_chunks)
    semantic_retriever = _EmbeddingSimilarityRetriever(
        docs=docs, doc_embeddings=doc_embeddings, embeddings=embeddings, k=k
    )

    evidence_by_requirement: dict[str, list[str]] = {}
    for requirement in jd_requirement_chunks:
        bm25_hits = bm25_retriever.invoke(requirement)
        semantic_hits = semantic_retriever.invoke(requirement)
        fused = _ensemble_rank(bm25_hits, semantic_hits, k=k)
        evidence_by_requirement[requirement] = [doc.page_content for doc in fused]
    return evidence_by_requirement


def _retrieve_with_query_variants(
    embeddings: OpenAIEmbeddings,
    resume_chunks: list[str],
    variants_by_requirement: dict[str, list[str]],
    top_k: int = _RETRIEVAL_TOP_K,
    doc_embeddings: list[list[float]] | None = None,
) -> dict[str, list[str]]:
    """Multi-query hybrid retrieval: each requirement carries several
    query phrasings, every one of them retrieves, and all the resulting
    rankings fuse into one evidence list per requirement.

    Keyed by requirement, not by query. Every variant is embedded in one
    batch and ranked in-process against the existing chunk embeddings,
    so expansion costs one embedding call in total rather than one per
    probe; that is why the cosine ranking is written out here."""
    if not resume_chunks:
        return {requirement: [] for requirement in variants_by_requirement}

    k = min(top_k, len(resume_chunks))
    docs = [Document(page_content=chunk) for chunk in resume_chunks]
    bm25_retriever = BM25Retriever.from_documents(docs, k=k, preprocess_func=_tokenize)
    if doc_embeddings is None or len(doc_embeddings) != len(resume_chunks):
        doc_embeddings = _embed(embeddings, resume_chunks)

    # dict.fromkeys, not set(): order-stable, and two requirements that
    # produced the same probe should not be embedded twice
    every_variant = list(
        dict.fromkeys(v for variants in variants_by_requirement.values() for v in variants if v.strip())
    )
    vector_by_variant = dict(zip(every_variant, _embed(embeddings, every_variant))) if every_variant else {}

    evidence_by_requirement: dict[str, list[str]] = {}
    for requirement, variants in variants_by_requirement.items():
        ranked_lists: list[list[Document]] = []
        for variant in variants:
            if not variant.strip():
                continue
            ranked_lists.append(bm25_retriever.invoke(variant))
            vector = vector_by_variant.get(variant)
            if vector is not None:
                scored = sorted(
                    zip(docs, doc_embeddings),
                    key=lambda pair: _cosine_similarity(vector, pair[1]),
                    reverse=True,
                )
                ranked_lists.append([doc for doc, _ in scored[:k]])
        evidence_by_requirement[requirement] = [
            doc.page_content for doc in _fuse_rankings(ranked_lists, k=k)
        ]
    return evidence_by_requirement
