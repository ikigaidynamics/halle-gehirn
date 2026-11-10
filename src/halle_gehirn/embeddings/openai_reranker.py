"""Logprobs-Reranker via OpenAI-kompatibles Backend.

Gleiche Logik wie LogprobsReranker, aber ueber OpenAI-API statt Ollama.
Funktioniert mit llama.cpp, vLLM, text-generation-inference, etc.
"""
from __future__ import annotations

import asyncio
import math
from typing import Any

import httpx
import structlog

from halle_gehirn.config import Settings, get_settings

logger = structlog.get_logger(__name__)

_RERANK_PROMPT = """\
Ist das folgende Dokument relevant fuer die Frage?

Dokument:
{document}

Frage: {query}

Antworte nur mit Ja oder Nein."""

_YES_TOKENS = frozenset({"Ja", "ja", "JA", "Yes", "yes", "YES"})


class OpenAIRerankerError(Exception):
    """Fehler beim OpenAI-Reranking."""


class OpenAIReranker:
    """Reranker via OpenAI-kompatible API.

    Bewertet jeden Treffer einzeln mit einer Ja/Nein-Frage.
    Parst die Antwort und gibt 1.0 fuer Ja, 0.0 fuer Nein.

    Args:
        settings: Optionale Settings-Instanz.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._base_url = self._settings.openai_base_url.rstrip("/")
        self._api_key = self._settings.openai_api_key or "no-key"
        self._model = self._settings.openai_model or self._settings.llm_model
        self._semaphore = asyncio.Semaphore(
            self._settings.context_concurrency,
        )

    async def rerank(
        self, query: str, hits: list[Any],
    ) -> list[Any]:
        """Sortiert Treffer nach LLM-Relevanz.

        Args:
            query: Die Benutzeranfrage.
            hits: Liste von RetrievalHit-Objekten.

        Returns:
            Dieselbe Liste, nach rerank_score absteigend sortiert.
        """
        if not hits:
            return hits

        tasks = [self._score_single(query, hit) for hit in hits]
        scores = await asyncio.gather(*tasks, return_exceptions=True)

        for hit, score in zip(hits, scores, strict=True):
            if isinstance(score, float):
                hit.rerank_score = score
            elif isinstance(score, Exception):
                logger.warning(
                    "openai_rerank_failed",
                    point_id=getattr(hit, "point_id", "?"),
                    error=str(score),
                )
                hit.rerank_score = 0.0
            else:
                hit.rerank_score = 0.0

        hits.sort(key=lambda h: h.rerank_score, reverse=True)

        logger.info(
            "openai_rerank_done",
            total=len(hits),
            top_score=hits[0].rerank_score if hits else 0.0,
        )
        return hits

    async def _score_single(self, query: str, hit: Any) -> float:
        """Bewertet einen einzelnen Treffer via OpenAI-API."""
        async with self._semaphore:
            text = _extract_text(hit)
            prompt = _RERANK_PROMPT.format(
                document=text[:2000],
                query=query,
            )

            url = f"{self._base_url}/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            }
            payload = {
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 10,
                "temperature": 0.0,
            }

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        url, json=payload, headers=headers,
                    )
                    if response.status_code != 200:
                        raise OpenAIRerankerError(
                            f"API error {response.status_code}"
                        )

                    data = response.json()
                    content = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        .strip()
                    )

                    return _parse_yes_no(content)

            except httpx.RequestError as exc:
                raise OpenAIRerankerError(f"Request failed: {exc}") from exc


def _extract_text(hit: Any) -> str:
    """Extrahiert den Text aus einem RetrievalHit."""
    if hasattr(hit, "payload") and isinstance(hit.payload, dict):
        payload = hit.payload
        header_parts: list[str] = []
        titel = payload.get("titel")
        if titel:
            header_parts.append(f"Titel: {titel}")
        datei = payload.get("datei")
        if datei:
            header_parts.append(f"Datei: {datei}")
        autor = payload.get("autor")
        if autor and isinstance(autor, list) and autor:
            header_parts.append("Autor: " + ", ".join(str(a) for a in autor))
        text = str(payload.get("text", ""))
        if header_parts:
            return "\n".join(header_parts) + "\n\n" + text
        return text
    return str(hit)


def _parse_yes_no(content: str) -> float:
    """Parst Ja/Nein aus der Text-Antwort."""
    cleaned = content.strip().lower()
    # Entferne evtl. Reasoning-Block
    if "</think>" in cleaned:
        cleaned = cleaned.split("</think>")[-1].strip()
    if cleaned in ("ja", "yes"):
        return 1.0
    if cleaned.startswith("ja") and (
        len(cleaned) == 2 or not cleaned[2].isalpha()
    ):
        return 1.0
    if cleaned.startswith("yes") and (
        len(cleaned) == 3 or not cleaned[3].isalpha()
    ):
        return 1.0
    return 0.0
