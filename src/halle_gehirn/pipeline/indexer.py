"""Indexierungs-Logik: Embedding + Qdrant-Upsert.

Wiederverwendbare async-Funktion fuer die Erzeugung von Embeddings
(dense + sparse) und den Qdrant-Upsert. Wird sowohl vom CLI-Script
(``scripts/reindex.py``) als auch von der Streamlit-UI genutzt.
"""
from __future__ import annotations

from dataclasses import dataclass

import structlog

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.embeddings.ollama_embedder import OllamaEmbedder
from halle_gehirn.embeddings.sparse_embedder import FastEmbedSparseEmbedder
from halle_gehirn.pipeline.progress import ProgressCallback, ProgressEvent
from halle_gehirn.vector_store.qdrant_client import (
    delete_stale_chunks,
    upsert_chunks,
)
from halle_gehirn.vector_store.schema import ChunkPayload

logger = structlog.get_logger(__name__)


@dataclass
class IndexResult:
    """Ergebnis eines Indexierungslaufs."""

    chunks_embedded: int = 0
    chunks_upserted: int = 0
    chunks_stale_deleted: int = 0


async def embed_and_upsert(
    payloads: list[ChunkPayload],
    settings: Settings | None = None,
    on_progress: ProgressCallback = None,
) -> IndexResult:
    """Erzeugt Embeddings, upserted in Qdrant und raeumt Altbestand auf.

    Nach erfolgreichem Upsert werden je Dokument veraltete Punkte
    entfernt (alte source_hashes derselben Datei sowie ueberzaehlige
    chunk_index-Werte) — Reihenfolge bewusst NACH dem Upsert, damit es
    kein Fenster gibt, in dem ein Dokument im Index fehlt.

    Args:
        payloads: Liste von ChunkPayloads.
        settings: Optionale Settings.
        on_progress: Optionaler Callback fuer Fortschrittsereignisse.

    Returns:
        IndexResult mit Statistiken.
    """
    s = settings or get_settings()
    texts = [p.text for p in payloads]

    dense_embedder = OllamaEmbedder(settings=s)
    sparse_embedder = FastEmbedSparseEmbedder(settings=s)

    logger.info("embedding_start", chunks=len(texts))
    if on_progress:
        on_progress(ProgressEvent(
            phase="embed",
            datei="(alle)",
            doc_index=0,
            doc_total=0,
            detail=f"Dense-Embedding fuer {len(texts)} Chunks...",
            chunks_total=len(texts),
        ))
    dense_vecs = await dense_embedder.embed(texts)
    if on_progress:
        on_progress(ProgressEvent(
            phase="embed",
            datei="(alle)",
            doc_index=0,
            doc_total=0,
            detail=f"Sparse-Embedding fuer {len(texts)} Chunks...",
            chunks_total=len(texts),
            chunks_so_far=len(texts),
        ))
    sparse_vecs = sparse_embedder.embed(texts)
    logger.info("embedding_done", dense=len(dense_vecs), sparse=len(sparse_vecs))

    if on_progress:
        on_progress(ProgressEvent(
            phase="upsert",
            datei="(alle)",
            doc_index=0,
            doc_total=0,
            detail=f"Upsert {len(payloads)} Chunks in Qdrant...",
            chunks_total=len(payloads),
        ))
    total = upsert_chunks(payloads, dense_vecs, sparse_vecs)
    logger.info("upsert_complete", total=total)

    stale = _cleanup_stale(payloads)

    return IndexResult(
        chunks_embedded=len(texts),
        chunks_upserted=total,
        chunks_stale_deleted=stale,
    )


def _cleanup_stale(payloads: list[ChunkPayload]) -> int:
    """Entfernt veraltete Punkte je Dokument (nach dem Upsert)."""
    # Erwartete Chunk-Anzahl je (datei, source_hash): max Index + 1
    expected: dict[tuple[str, str], int] = {}
    for p in payloads:
        key = (p.datei, p.source_hash)
        expected[key] = max(expected.get(key, 0), p.chunk_index + 1)

    stale_total = 0
    for (datei, source_hash), count in expected.items():
        stale_total += delete_stale_chunks(datei, source_hash, count)
    if stale_total:
        logger.info("stale_cleanup_done", deleted=stale_total)
    return stale_total
