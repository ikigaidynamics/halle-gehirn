"""Sparse-Embedder via FastEmbed BM25 (deutsch).

Erzeugt spaerliche BM25-Vektoren mit deutschem Stemming fuer
lexikalische Suche (Namen, Codes, Fachbegriffe).
"""
from __future__ import annotations

from typing import Any

import structlog
from fastembed import SparseTextEmbedding

from halle_gehirn.config import Settings, get_settings

logger = structlog.get_logger(__name__)


class FastEmbedSparseEmbedder:
    """Sparse-Embedder mit FastEmbed BM25.

    Verwendet das konfigurierte Sparse-Modell (Default: Qdrant/bm25)
    mit deutscher Sprache fuer Stemming.

    Args:
        settings: Optionale Settings-Instanz.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._model: SparseTextEmbedding | None = None

    def _get_model(self) -> SparseTextEmbedding:
        """Lazy-Initialisierung des Sparse-Modells."""
        if self._model is None:
            logger.info(
                "sparse_model_init",
                model=self._settings.sparse_model,
                language=self._settings.sparse_language,
            )
            self._model = SparseTextEmbedding(
                model_name=self._settings.sparse_model,
                language=self._settings.sparse_language,
            )
        return self._model

    def embed(self, texts: list[str]) -> list[Any]:
        """Erzeugt Sparse-Vektoren fuer eine Liste von Texten.

        Args:
            texts: Liste von Texten.

        Returns:
            Liste von Sparse-Embedding-Objekten (indices + values).
        """
        if not texts:
            return []
        model = self._get_model()
        results = list(model.embed(texts))
        logger.debug(
            "sparse_embed_done",
            count=len(texts),
            model=self._settings.sparse_model,
        )
        return results
