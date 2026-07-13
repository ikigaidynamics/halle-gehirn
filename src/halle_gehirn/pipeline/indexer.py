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
from halle_gehirn.vector_store.qdrant_client import upsert_chunks
from halle_gehirn.vector_store.schema import ChunkPayload

logger = structlog.get_logger(__name__)


@dataclass
class IndexResult:
    """Ergebnis eines Indexierungslaufs."""

    chunks_embedded: int = 0
    chunks_upserted: int = 0


async def embed_and_upsert(
    payloads: list[ChunkPayload],
    settings: Settings | None = None,
) -> IndexResult:
    """Erzeugt Embeddings und upserted in Qdrant.

    Args:
        payloads: Liste von ChunkPayloads.
        settings: Optionale Settings.

    Returns:
        IndexResult mit Statistiken.
    """
    s = settings or get_settings()
    texts = [p.text for p in payloads]

    dense_embedder = OllamaEmbedder(settings=s)
    sparse_embedder = FastEmbedSparseEmbedder(settings=s)

    logger.info("embedding_start", chunks=len(texts))
    dense_vecs = await dense_embedder.embed(texts)
    sparse_vecs = sparse_embedder.embed(texts)
    logger.info("embedding_done", dense=len(dense_vecs), sparse=len(sparse_vecs))

    total = upsert_chunks(payloads, dense_vecs, sparse_vecs)
    logger.info("upsert_complete", total=total)

    return IndexResult(chunks_embedded=len(texts), chunks_upserted=total)
