"""Embedder-Abstraktionen und Factory-Funktionen.

Stellt ``get_dense_embedder()`` und ``get_sparse_embedder()`` bereit,
die je nach Config die passende Implementierung zurueckgeben.
Matryoshka-Truncation fuer Dense-Vektoren wird hier zentral angewendet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING

from halle_gehirn.config import Settings, get_settings

if TYPE_CHECKING:
    from halle_gehirn.embeddings.ollama_embedder import OllamaEmbedder
    from halle_gehirn.embeddings.sparse_embedder import FastEmbedSparseEmbedder


@dataclass
class EmbeddingResult:
    """Ergebnis einer Embedding-Operation (dense oder sparse)."""

    vectors: list[list[float]] = field(default_factory=list)
    model: str = ""
    dim: int = 0


def truncate_matryoshka(
    vectors: list[list[float]], target_dim: int,
) -> list[list[float]]:
    """Kuerzt Matryoshka-Vektoren auf *target_dim* Dimensionen.

    Args:
        vectors: Liste von Embedding-Vektoren.
        target_dim: Zieldimension (z.B. 1024).

    Returns:
        Gekuerzte Vektoren.
    """
    return [v[:target_dim] for v in vectors]


@lru_cache(maxsize=1)
def get_dense_embedder(
    settings: Settings | None = None,
) -> OllamaEmbedder:
    """Gibt den konfigurierten Dense-Embedder zurueck (gecacht).

    Args:
        settings: Optionale Settings-Instanz.

    Returns:
        OllamaEmbedder-Instanz.
    """
    from halle_gehirn.embeddings.ollama_embedder import OllamaEmbedder

    s = settings or get_settings()
    return OllamaEmbedder(settings=s)


@lru_cache(maxsize=1)
def get_sparse_embedder(
    settings: Settings | None = None,
) -> FastEmbedSparseEmbedder:
    """Gibt den konfigurierten Sparse-Embedder zurueck (gecacht).

    Args:
        settings: Optionale Settings-Instanz.

    Returns:
        FastEmbedSparseEmbedder-Instanz.
    """
    from halle_gehirn.embeddings.sparse_embedder import FastEmbedSparseEmbedder

    s = settings or get_settings()
    return FastEmbedSparseEmbedder(settings=s)
