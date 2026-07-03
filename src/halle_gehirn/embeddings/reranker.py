"""Logprobs-Reranker via Ollama — Phase 4.

Sortiert Retrieval-Kandidaten nach Relevanz anhand der Token-Logprobs
des LLMs. Stellt eine binaere Ja/Nein-Frage pro Treffer und extrahiert
P(Ja) aus den Logprobs des ersten Antwort-Tokens — ergibt ein
kontinuierliches 0.0-1.0-Mass, das direkt zur Confidence-Ampel
(CONF_GREEN/CONF_YELLOW) passt.

Verwendet ``think=False`` + ``num_predict=8``, um qwen3-Think-Bloecke
vollstaendig zu unterdruecken. Fallback auf Text-Parsing, falls
Logprobs nicht verfuegbar (aeltere Ollama-Versionen).
"""
from __future__ import annotations

import asyncio
import math
import re
from typing import Any

import ollama
import structlog

from halle_gehirn.config import Settings, get_settings

logger = structlog.get_logger(__name__)

# Binaerer Relevanz-Prompt (Ja/Nein)
_RERANK_PROMPT = """\
Ist das folgende Dokument relevant fuer die Frage?

Dokument:
{document}

Frage: {query}

Antworte nur mit Ja oder Nein."""

# Token-Varianten fuer "Ja" (case-insensitive, mit/ohne Leerzeichen)
_YES_TOKENS = frozenset({"Ja", "ja", "JA", "Yes", "yes", "YES"})


class RerankerError(Exception):
    """Fehler beim Reranking."""


class LogprobsReranker:
    """Logprobs-Reranker via Ollama.

    Bewertet jeden Treffer einzeln: binaere Ja/Nein-Frage an das LLM,
    Score = P(Ja) aus den Token-Logprobs des ersten Antwort-Tokens.
    Ergibt ein kontinuierliches 0.0-1.0-Mass.

    Verwendet sync ``ollama.Client`` + ``asyncio.to_thread()``
    (gleicher Ansatz wie OllamaEmbedder, da AsyncClient auf
    Windows ConnectErrors zeigt).

    Args:
        settings: Optionale Settings-Instanz.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = ollama.Client(host=self._settings.ollama_url)
        self._model = self._settings.llm_model
        self._num_predict = self._settings.rerank_num_predict
        self._top_logprobs = self._settings.rerank_top_logprobs
        self._semaphore = asyncio.Semaphore(
            self._settings.context_concurrency,
        )

    async def rerank(
        self, query: str, hits: list[Any],
    ) -> list[Any]:
        """Sortiert Treffer nach LLM-Relevanz (P(Ja) aus Logprobs).

        Args:
            query: Die Benutzeranfrage.
            hits: Liste von RetrievalHit-Objekten.

        Returns:
            Dieselbe Liste, nach rerank_score absteigend sortiert.
            Jeder Hit erhaelt ein neues Attribut ``rerank_score``.
        """
        if not hits:
            return hits

        tasks = [
            self._score_single(query, hit)
            for hit in hits
        ]
        scores = await asyncio.gather(*tasks, return_exceptions=True)

        for hit, score in zip(hits, scores, strict=True):
            if isinstance(score, float):
                hit.rerank_score = score
            elif isinstance(score, Exception):
                logger.warning(
                    "rerank_score_failed",
                    point_id=getattr(hit, "point_id", "?"),
                    error=str(score),
                )
                hit.rerank_score = 0.0
            else:
                hit.rerank_score = 0.0

        hits.sort(key=lambda h: h.rerank_score, reverse=True)
        logger.info(
            "rerank_done",
            total=len(hits),
            top_score=hits[0].rerank_score if hits else 0.0,
        )
        return hits

    async def _score_single(self, query: str, hit: Any) -> float:
        """Bewertet einen einzelnen Treffer via LLM-Logprobs."""
        async with self._semaphore:
            text = _extract_text(hit)
            prompt = _RERANK_PROMPT.format(
                document=text[:2000],
                query=query,
            )
            response = await asyncio.to_thread(
                self._client.chat,
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                think=False,
                logprobs=True,
                top_logprobs=self._top_logprobs,
                options={
                    "temperature": 0.0,
                    "num_predict": self._num_predict,
                },
            )

            # Primaer: Score aus Logprobs extrahieren
            logprobs_data = response.get("logprobs") or []
            if logprobs_data:
                score = _extract_yes_prob(logprobs_data)
                logger.debug(
                    "rerank_logprobs",
                    point_id=getattr(hit, "point_id", "?"),
                    first_token=logprobs_data[0].get("token", "?"),
                    score=round(score, 4),
                )
                return score

            # Fallback: Text-Parsing (Ja=1.0, Nein=0.0)
            content: str = response["message"]["content"].strip()
            content = _strip_think_tags(content)
            fallback = _parse_yes_no(content)
            logger.warning(
                "rerank_logprobs_unavailable",
                point_id=getattr(hit, "point_id", "?"),
                content=content[:50],
                fallback_score=fallback,
            )
            return fallback


def _extract_text(hit: Any) -> str:
    """Extrahiert den Text aus einem RetrievalHit."""
    if hasattr(hit, "payload") and isinstance(hit.payload, dict):
        return str(hit.payload.get("text", ""))
    return str(hit)


def _extract_yes_prob(logprobs_data: list[dict[str, Any]]) -> float:
    """Extrahiert P(Ja) aus den Logprobs des ersten Tokens.

    Sucht in den top_logprobs des ersten Token-Slots nach einem
    affirmativen Token (Ja/ja/Yes/yes). Gibt exp(logprob) zurueck —
    eine Wahrscheinlichkeit im Bereich [0.0, 1.0].

    Args:
        logprobs_data: Liste von Logprob-Dicts aus der Ollama-Response.

    Returns:
        P(Ja) als Float (0.0 falls kein affirmatives Token gefunden).
    """
    if not logprobs_data:
        return 0.0

    first = logprobs_data[0]

    # Zuerst: Ist das generierte Token selbst ein Ja-Token?
    generated = first.get("token", "").strip()
    if generated in _YES_TOKENS:
        return math.exp(first.get("logprob", -10.0))

    # Sonst: Suche in top_logprobs nach einem Ja-Token
    for alt in first.get("top_logprobs", []):
        token = alt.get("token", "").strip()
        if token in _YES_TOKENS:
            return math.exp(alt.get("logprob", -10.0))

    # Kein Ja-Token unter den Top-Kandidaten → sehr unwahrscheinlich
    return 0.0


def _parse_yes_no(content: str) -> float:
    """Fallback: Parst Ja/Nein aus der Text-Antwort.

    Gibt 1.0 fuer Ja, 0.0 fuer Nein, 0.0 fuer alles andere.
    """
    cleaned = content.strip().lower().rstrip(".")
    if cleaned in ("ja", "yes"):
        return 1.0
    return 0.0


def _strip_think_tags(text: str) -> str:
    """Extrahiert die Antwort nach <think>-Block (qwen3).

    Identisch zu context_enricher._strip_think_tags.
    """
    if "<think>" not in text:
        return text.strip()
    match = re.search(r"</think>\s*(.*)", text, flags=re.DOTALL)
    if match and match.group(1).strip():
        return match.group(1).strip()
    inner = re.search(r"<think>(.*?)</think>", text, flags=re.DOTALL)
    if inner and inner.group(1).strip():
        return inner.group(1).strip()
    return ""
