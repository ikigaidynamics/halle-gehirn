"""Faithfulness/NLI-Grounding -- Phase 5.

Anti-Halluzination Stufe 3: Verifiziert die generierte Antwort gegen
den Retrieval-Kontext. Prueft pro Satz, ob er durch die Quellen
gestuetzt ist. Deaktivierbar via USE_GROUNDING_CHECK=false.

Verwendet think=False + /no_think (wie Reranker -- binaere Bewertung).
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

import ollama
import structlog

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.llm_utils import strip_think_tags

logger = structlog.get_logger(__name__)

_GROUNDING_PROMPT = """\
/no_think
Kontext (Quellen mit Metadaten und Text):
{context}

Die Metadaten jeder Quelle (Titel, Datei, Autor) sind verifizierte Fakten \
und duerfen zur Stuetzung herangezogen werden. Wenn ein Dateiname einen \
Autorennamen enthaelt, gilt die Quelle als Arbeit dieses Autors.

Satz: {sentence}

Ist dieser Satz durch den Kontext (inkl. Metadaten) gestuetzt? \
Antworte NUR mit Ja oder Nein."""

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class GroundingResult:
    """Ergebnis der Faithfulness-Pruefung."""

    grounded: bool
    score: float  # Anteil gestuetzter Saetze (0.0-1.0)
    total_sentences: int = 0
    grounded_sentences: int = 0
    flagged_sentences: list[str] = field(default_factory=list)


class FaithfulnessChecker:
    """LLM-basierter Faithfulness/NLI-Checker.

    Prueft jeden nicht-trivialen Satz der Antwort gegen den
    Retrieval-Kontext. Nutzt das konfigurierte LLM mit binaerer
    Ja/Nein-Bewertung.

    Args:
        settings: Optionale Settings-Instanz.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = ollama.Client(host=self._settings.ollama_url)
        self._model = self._settings.llm_model
        self._threshold = self._settings.grounding_threshold

    async def check(
        self, answer: str, context: list[Any],
    ) -> GroundingResult:
        """Prueft die Faithfulness der Antwort.

        Args:
            answer: Die generierte Antwort.
            context: RetrievalHit-Objekte als Kontext.

        Returns:
            GroundingResult mit Score und geflaggten Saetzen.
        """
        if not self._settings.use_grounding_check:
            return GroundingResult(grounded=True, score=1.0)

        context_text = _format_context(context)
        sentences = _extract_sentences(answer)

        if not sentences:
            return GroundingResult(grounded=True, score=1.0)

        tasks = [
            self._check_sentence(sent, context_text)
            for sent in sentences
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        grounded_count = 0
        flagged: list[str] = []
        for sent, result in zip(sentences, results, strict=True):
            if isinstance(result, bool) and result:
                grounded_count += 1
            else:
                flagged.append(sent)

        score = grounded_count / len(sentences) if sentences else 1.0
        is_grounded = score >= self._threshold

        logger.info(
            "grounding_check_done",
            total=len(sentences),
            grounded=grounded_count,
            flagged=len(flagged),
            score=round(score, 3),
        )

        return GroundingResult(
            grounded=is_grounded,
            score=score,
            total_sentences=len(sentences),
            grounded_sentences=grounded_count,
            flagged_sentences=flagged,
        )

    async def _check_sentence(
        self, sentence: str, context: str,
    ) -> bool:
        """Prueft einen einzelnen Satz gegen den Kontext."""
        prompt = _GROUNDING_PROMPT.format(
            context=context[:3000],
            sentence=sentence,
        )
        try:
            response = await asyncio.to_thread(
                self._client.chat,
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                think=False,
                options={"temperature": 0.0, "num_predict": 8},
            )
            content = response["message"]["content"].strip()
            content = strip_think_tags(content)
            content = content.lower()
            return bool(content.startswith("ja"))
        except Exception as exc:
            logger.warning("grounding_sentence_failed", error=str(exc))
            return False  # Bei Fehler: flaggen (fail-safe)


def _format_context(hits: list[Any]) -> str:
    """Formatiert RetrievalHits als Kontext-Text.

    Enthaelt Titel, Datei und Autor neben dem Chunk-Text, damit der
    Grounding-Check auch metadatenbasierte Aussagen (z.B. "die Arbeit
    von Wang beschreibt...") verifizieren kann.
    """
    parts: list[str] = []
    for hit in hits:
        payload = getattr(hit, "payload", {}) or {}
        text = payload.get("text", "")
        if not text:
            continue
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
        if header_parts:
            parts.append(" · ".join(header_parts) + "\n" + text)
        else:
            parts.append(text)
    return "\n\n".join(parts)


def _extract_sentences(text: str) -> list[str]:
    """Extrahiert nicht-triviale Saetze aus dem Text."""
    sentences = _SENTENCE_SPLIT.split(text)
    return [
        s.strip() for s in sentences
        if len(s.strip()) >= 20
        and not s.strip().lower().startswith(("quelle", "verwendete quellen", "hinweis:"))
    ]
