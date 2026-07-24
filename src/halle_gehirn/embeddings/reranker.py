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

        all_zero = all(h.rerank_score == 0.0 for h in hits)
        if all_zero and hits:
            logger.warning(
                "rerank_all_scores_zero",
                total=len(hits),
                hint="Moeglicherweise unterstuetzt das Modell keine "
                     "Logprobs oder die Token-Erkennung schlaegt fehl. "
                     "Log-Level DEBUG fuer Details.",
            )

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
            if isinstance(response, dict):
                logprobs_data = response.get("logprobs") or []
            else:
                logprobs_data = getattr(response, "logprobs", None) or []
            if logprobs_data:
                score = _extract_yes_prob(logprobs_data)
                first_tok = getattr(logprobs_data[0], "token", "?")
                logger.debug(
                    "rerank_logprobs",
                    point_id=getattr(hit, "point_id", "?"),
                    first_token=first_tok,
                    score=round(score, 4),
                )
                return score

            # Fallback: Text-Parsing (Ja=1.0, Nein=0.0)
            msg = getattr(response, "message", None)
            content: str = (msg.content if msg else "").strip()
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


def _extract_yes_prob(logprobs_data: list[Any]) -> float:
    """Extrahiert P(Ja) aus den Logprobs des ersten Tokens.

    Sucht in den top_logprobs des ersten Token-Slots nach einem
    affirmativen Token (Ja/ja/Yes/yes). Gibt exp(logprob) zurueck —
    eine Wahrscheinlichkeit im Bereich [0.0, 1.0].

    Robuste Variante: strippt Whitespace und Interpunktion,
    prueft case-insensitive als Fallback.

    Args:
        logprobs_data: Liste von Logprob-Eintraegen (Dicts oder Objekte).

    Returns:
        P(Ja) als Float (0.0 falls kein affirmatives Token gefunden).
    """
    if not logprobs_data:
        return 0.0

    # Iteriere ueber Logprob-Eintraege (ueberspringe Whitespace-Tokens,
    # z.B. fuehrendes "\n" oder " " vor "Ja"/"Nein").
    for entry in logprobs_data:
        generated = _get(entry, "token", "").strip()
        if not generated:
            continue  # Whitespace-Token ueberspringen

        # Ist das generierte Token selbst ein Ja-Token?
        prob = _match_yes_token(generated, _get(entry, "logprob", -10.0))
        if prob is not None:
            return prob

        # Sonst: Suche in top_logprobs nach einem Ja-Token
        top = _get(entry, "top_logprobs", None) or []
        for alt in top:
            token = _get(alt, "token", "").strip()
            prob = _match_yes_token(token, _get(alt, "logprob", -10.0))
            if prob is not None:
                return prob

        # Erstes nicht-leeres Token gefunden, aber kein Ja-Match
        logger.debug(
            "rerank_no_yes_token",
            generated_token=repr(generated),
            top_tokens=[repr(_get(a, "token", "?")) for a in top],
        )
        return 0.0

    return 0.0


def _match_yes_token(token: str, logprob: float) -> float | None:
    """Prueft ob ein Token ein affirmatives Token ist.

    Erkennt exakte Matches, case-insensitive Matches und
    Tokens mit angehaengter Interpunktion (z.B. 'Ja.', 'Ja,').

    Args:
        token: Der Token-String (bereits gestrippt).
        logprob: Der Log-Wahrscheinlichkeitswert.

    Returns:
        exp(logprob) bei Match, sonst None.
    """
    if not token:
        return None
    if token in _YES_TOKENS:
        return math.exp(logprob)
    cleaned = token.strip(".,!?;: ").lower()
    if cleaned in ("ja", "yes"):
        return math.exp(logprob)
    return None


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Liest ein Feld aus einem Dict oder Objekt (ollama-kompatibel)."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _parse_yes_no(content: str) -> float:
    """Fallback: Parst Ja/Nein aus der Text-Antwort.

    Erkennt auch Varianten wie 'Ja, ...' oder 'Ja.' am Anfang.
    Gibt 1.0 fuer Ja, 0.0 fuer alles andere.
    """
    cleaned = content.strip().lower()
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


from halle_gehirn.llm_utils import strip_think_tags as _strip_think_tags  # noqa: E402
