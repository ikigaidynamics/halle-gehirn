"""Dense-Embedder via OpenAI-kompatibler API.

Erzeugt dichte Vektoren ueber eine OpenAI-kompatible API (vLLM, TEI, etc.)
mit Batching, Retry+Backoff und Matryoshka-Truncation auf EMBEDDING_DIM.
"""
from __future__ import annotations

import asyncio

import httpx
import structlog

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.embeddings.provider import truncate_matryoshka
from halle_gehirn.pipeline.chunker import count_tokens

logger = structlog.get_logger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0  # Sekunden
_BATCH_SIZE = 32
_TIMEOUT = 60.0  # Sekunden


class OpenAIEmbedderError(Exception):
    """Fehler bei der OpenAI-Embedding-Erzeugung."""


class OpenAIEmbedder:
    """Dense-Embedder ueber OpenAI-kompatible API.

    Verwendet das konfigurierte Embedding-Modell und kuerzt die Vektoren
    auf EMBEDDING_DIM (Matryoshka).

    Args:
        settings: Optionale Settings-Instanz.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._base_url = self._settings.embedding_openai_base_url.rstrip("/")
        self._api_key = self._settings.embedding_openai_api_key or "dummy"
        # Verwende embedding_openai_model falls gesetzt, sonst embedding_model
        self._model = (
            self._settings.embedding_openai_model
            or self._settings.embedding_model
        )
        self._dim = self._settings.embedding_dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Erzeugt Dense-Vektoren fuer eine Liste von Texten.

        Args:
            texts: Liste von Texten.

        Returns:
            Liste von Embedding-Vektoren (Laenge = EMBEDDING_DIM).

        Raises:
            OpenAIEmbedderError: Embedding-Erzeugung fehlgeschlagen.
        """
        if not texts:
            return []

        # Warnung bei uebergrossen Texten
        max_tok = self._settings.chunk_max_tokens
        for i, text in enumerate(texts):
            tok = count_tokens(text)
            if tok > max_tok:
                logger.warning(
                    "embedding_text_oversized",
                    text_index=i,
                    tokens=tok,
                    limit=max_tok,
                    preview=text[:80],
                    hint="Embedding-Modell schneidet evtl. still ab",
                )

        all_vectors: list[list[float]] = []
        for batch_start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[batch_start : batch_start + _BATCH_SIZE]
            vectors = await self._embed_batch(batch)
            all_vectors.extend(vectors)

        return truncate_matryoshka(all_vectors, self._dim)

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Erzeugt Embeddings fuer einen Batch mit Retry."""
        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    response = await client.post(
                        f"{self._base_url}/embeddings",
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": self._model,
                            "input": texts,
                        },
                    )
                    response.raise_for_status()
                    data = response.json()

                # OpenAI-Format: {"data": [{"embedding": [...], "index": 0}, ...]}
                embeddings_data = sorted(data["data"], key=lambda x: x["index"])
                embeddings = [item["embedding"] for item in embeddings_data]

                logger.debug(
                    "openai_embed_batch",
                    model=self._model,
                    count=len(texts),
                    raw_dim=len(embeddings[0]) if embeddings else 0,
                    attempt=attempt,
                )
                return embeddings

            except Exception as exc:
                last_error = exc
                if attempt < _MAX_RETRIES:
                    wait = _BACKOFF_BASE * (2 ** (attempt - 1))
                    logger.warning(
                        "openai_embed_retry",
                        attempt=attempt,
                        wait_s=wait,
                        error=str(exc),
                    )
                    await asyncio.sleep(wait)

        raise OpenAIEmbedderError(
            f"Embedding fehlgeschlagen nach {_MAX_RETRIES} Versuchen: {last_error}"
        ) from last_error
