"""Dense-Embedder via FastEmbed (lokal, kein Ollama noetig).

Erzeugt dichte Vektoren ueber FastEmbed mit multilingualen Modellen.
Laeuft vollstaendig lokal auf CPU.
"""
from __future__ import annotations

import asyncio
from functools import lru_cache

import structlog

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.embeddings.provider import truncate_matryoshka

logger = structlog.get_logger(__name__)

_BATCH_SIZE = 32

# Gutes multilinguales Modell fuer Deutsch
_DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class FastEmbedDenseError(Exception):
    """Fehler bei der FastEmbed-Embedding-Erzeugung."""


@lru_cache(maxsize=1)
def _get_model(model_name: str):
    """Laedt das FastEmbed-Modell (gecacht)."""
    from fastembed import TextEmbedding

    logger.info("fastembed_loading_model", model=model_name)
    return TextEmbedding(model_name=model_name)


class FastEmbedDenseEmbedder:
    """Dense-Embedder ueber FastEmbed.

    Verwendet ein multilinguales Sentence-Transformer-Modell
    und laeuft vollstaendig lokal ohne externe Dienste.

    Args:
        settings: Optionale Settings-Instanz.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._model_name = self._settings.fastembed_model or _DEFAULT_MODEL
        self._dim = self._settings.embedding_dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Erzeugt Dense-Vektoren fuer eine Liste von Texten.

        Args:
            texts: Liste von Texten.

        Returns:
            Liste von Embedding-Vektoren (Laenge = EMBEDDING_DIM).

        Raises:
            FastEmbedDenseError: Embedding-Erzeugung fehlgeschlagen.
        """
        if not texts:
            return []

        try:
            model = _get_model(self._model_name)
            # FastEmbed erwartet eine Liste und gibt einen Generator zurueck
            embeddings = await asyncio.to_thread(
                lambda: list(model.embed(texts))
            )
            # Konvertiere numpy arrays zu Listen
            vectors = [list(emb) for emb in embeddings]

            logger.debug(
                "fastembed_dense_done",
                model=self._model_name,
                count=len(texts),
                raw_dim=len(vectors[0]) if vectors else 0,
                target_dim=self._dim,
            )

            return truncate_matryoshka(vectors, self._dim)

        except Exception as exc:
            raise FastEmbedDenseError(
                f"FastEmbed Dense-Embedding fehlgeschlagen: {exc}"
            ) from exc
