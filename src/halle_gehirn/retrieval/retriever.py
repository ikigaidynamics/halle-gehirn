"""Hybrid + RRF + MMR + Rerank — Phase 4.

Orchestriert den vollstaendigen Retrieval-Pfad:
1. Query-Transformation (optional, wenn USE_QUERY_TRANSFORM=true)
2. Dense + Sparse Embedding der Query
3. Hybrid Query (Qdrant: prefetch dense+sparse → RRF Fusion)
4. MMR-Diversifizierung (optional, wenn USE_MMR=true)
5. Reranking (Logprobs via Ollama)
6. Top-K-Selektion (TOP_K_FINAL)
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.embeddings.provider import get_dense_embedder
from halle_gehirn.embeddings.sparse_embedder import FastEmbedSparseEmbedder
from halle_gehirn.retrieval.router import KeywordRouter
from halle_gehirn.vector_store.qdrant_client import (
    RetrievalHit,
    hybrid_query,
)

if TYPE_CHECKING:
    from halle_gehirn.observability.retrieval_logger import PipelineTimer

logger = structlog.get_logger(__name__)


class HybridRetriever:
    """Vollstaendiger Retrieval-Orchestrator.

    Kombiniert Dense+Sparse Embedding, Hybrid Query, MMR und Reranking
    zu einem einzigen ``retrieve()``-Aufruf.

    Args:
        settings: Optionale Settings-Instanz.
        dense_embedder: Optionaler Dense-Embedder.
        sparse_embedder: Optionaler Sparse-Embedder.
        reranker: Optionaler Reranker.
        router: Optionaler Router.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        dense_embedder: Any | None = None,
        sparse_embedder: FastEmbedSparseEmbedder | None = None,
        reranker: Any | None = None,
        router: KeywordRouter | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._dense = dense_embedder or get_dense_embedder()
        self._sparse = sparse_embedder or FastEmbedSparseEmbedder(
            settings=self._settings,
        )
        self._reranker = reranker or _get_reranker(self._settings)
        self._router = router or KeywordRouter(settings=self._settings)

    async def retrieve(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        timer: PipelineTimer | None = None,
    ) -> list[RetrievalHit]:
        """Fuehrt den vollstaendigen Retrieval-Pfad aus.

        Args:
            query: Die Benutzeranfrage.
            filters: Optionale Payload-Filter (key -> value/list).
            timer: Optionaler PipelineTimer fuer Latenz-Messung.

        Returns:
            Top-K RetrievalHit-Objekte mit rerank_score.
        """
        # 1. Router — Query-Typ bestimmen
        query_type = self._router.route(query)
        logger.info("retrieval_start", query_type=query_type)

        # 2. Embed Query (dense + sparse)
        if timer:
            timer.start("embed")
        dense_vecs = await self._dense.embed([query])
        query_dense = dense_vecs[0]
        sparse_vecs = self._sparse.embed([query])
        query_sparse = sparse_vecs[0]
        if timer:
            timer.stop("embed")

        # 3. Hybrid Query (Qdrant: prefetch → RRF)
        if timer:
            timer.start("search")
        hits = hybrid_query(
            query_dense=query_dense,
            query_sparse=query_sparse,
            limit=self._settings.top_k_initial,
            filters=filters,
        )
        if timer:
            timer.stop("search")
        logger.info(
            "hybrid_query_result",
            hits=len(hits),
            top_k_initial=self._settings.top_k_initial,
        )

        if not hits:
            return []

        # 4. MMR-Diversifizierung (optional)
        if self._settings.use_mmr and len(hits) > 1:
            hits = _mmr_reorder(
                hits,
                query_dense,
                lam=self._settings.mmr_lambda,
            )

        # 5. Reranking
        if timer:
            timer.start("rerank")
        hits = await self._reranker.rerank(query, hits)
        if timer:
            timer.stop("rerank")

        # 6. Top-K Final
        final = hits[: self._settings.top_k_final]
        logger.info(
            "retrieval_done",
            final_hits=len(final),
            top_score=final[0].rerank_score if final else 0.0,
            query_type=query_type,
        )
        return final


def _mmr_reorder(
    hits: list[Any],
    query_vec: list[float],
    lam: float = 0.7,
) -> list[Any]:
    """Maximal Marginal Relevance — Diversifizierung.

    Sortiert die Treffer so um, dass Relevanz und Diversitaet
    balanciert werden. Arbeitet auf den RRF-Scores (da keine
    Dense-Vektoren der Treffer im Payload vorliegen, wird der
    RRF-Score als Relevanz-Proxy verwendet).

    Args:
        hits: Treffer aus der Hybrid-Query.
        query_vec: Dense-Query-Vektor (fuer kuenftige Cosine-Sim).
        lam: Trade-off Relevanz vs. Diversitaet (0=max diverse, 1=max relevant).

    Returns:
        Umgeordnete Treffer-Liste.
    """
    if len(hits) <= 1:
        return hits

    selected: list[Any] = []
    remaining = list(hits)

    # Erster Treffer: hoechster Score
    remaining.sort(key=lambda h: h.score, reverse=True)
    selected.append(remaining.pop(0))

    while remaining:
        best_idx = 0
        best_mmr = -float("inf")
        for idx, candidate in enumerate(remaining):
            relevance = candidate.score
            # Diversitaet: minimale Textaehnlichkeit zu bereits gewaehlten
            max_sim = max(
                _text_jaccard(candidate, sel) for sel in selected
            )
            mmr = lam * relevance - (1 - lam) * max_sim
            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = idx
        selected.append(remaining.pop(best_idx))

    return selected


def _text_jaccard(a: Any, b: Any) -> float:
    """Jaccard-Aehnlichkeit der Chunk-Texte (Token-basiert).

    Leichtgewichtige Approximation fuer MMR-Diversitaet,
    da Dense-Vektoren der Chunks nicht im Payload sind.
    """
    text_a = a.payload.get("text", "")
    text_b = b.payload.get("text", "")
    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union > 0 else 0.0


class NoOpReranker:
    """Dummy-Reranker der nur den RRF-Score uebernimmt (kein LLM).

    Schnellste Option: Ueberspringt LLM-Reranking komplett und
    verwendet die Scores aus der Hybrid-Query direkt.
    """

    async def rerank(self, query: str, hits: list[Any]) -> list[Any]:
        """Kopiert score nach rerank_score ohne LLM-Aufruf."""
        for hit in hits:
            hit.rerank_score = getattr(hit, "score", 0.0)
        hits.sort(key=lambda h: h.rerank_score, reverse=True)
        logger.info("noop_rerank_done", total=len(hits))
        return hits


def _get_reranker(settings: Settings) -> Any:
    """Waehlt den Reranker basierend auf Konfiguration.

    Optionen:
    - none: Kein Reranking, nur RRF-Score (schnellste Option)
    - logprobs: LLM-basiertes Ja/Nein-Scoring (langsam aber genau)
    - cross_encoder: Dediziertes Reranking-Modell (TODO)
    - cohere: Cohere API (TODO)
    """
    if settings.reranker == "none":
        logger.info("reranker_disabled", msg="Verwende RRF-Score ohne LLM-Reranking")
        return NoOpReranker()

    if settings.llm_backend == "openai":
        from halle_gehirn.embeddings.openai_reranker import OpenAIReranker
        return OpenAIReranker(settings=settings)

    from halle_gehirn.embeddings.reranker import LogprobsReranker
    return LogprobsReranker(settings=settings)
