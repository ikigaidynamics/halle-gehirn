"""Ampel-Confidence-Gate — Phase 4.

Bewertet die Qualitaet der Retrieval-Ergebnisse anhand der
Reranker-Scores und gibt eine Ampelstufe zurueck:

- **gruen** (>= CONF_GREEN): Hohe Konfidenz, Antwort direkt generieren.
- **gelb** (>= CONF_YELLOW): Mittlere Konfidenz, Antwort mit Hedge.
- **rot** (< CONF_YELLOW): Niedrige Konfidenz, Refusal + Kontakthinweis.

Anti-Halluzination Stufe 1 (von 4): Confidence → URL-Whitelist →
Citation-Enforcement → Grounding-Check.
"""
from __future__ import annotations

from typing import Any

import structlog

from halle_gehirn.config import Settings, get_settings

logger = structlog.get_logger(__name__)

# Ampelstufen als Konstanten
GRUEN = "gruen"
GELB = "gelb"
ROT = "rot"


class ConfidenceGate:
    """Ampel-basiertes Confidence-Gate.

    Bewertet die Top-K-Treffer anhand ihrer Reranker-Scores und
    klassifiziert die Ergebnis-Qualitaet in drei Stufen.

    Args:
        settings: Optionale Settings-Instanz.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._green = self._settings.conf_green
        self._yellow = self._settings.conf_yellow

    def assess(self, hits: list[Any]) -> str:
        """Bewertet die Konfidenz der Retrieval-Ergebnisse.

        Verwendet den hoechsten rerank_score (oder score als Fallback)
        unter den Treffern. Bei leerer Liste: rot.

        Args:
            hits: Liste von RetrievalHit-Objekten mit score/rerank_score.

        Returns:
            Ampelstufe: 'gruen', 'gelb' oder 'rot'.
        """
        if not hits:
            logger.info("confidence_assessed", level=ROT, reason="no_hits")
            return ROT

        top_score = _best_score(hits)
        level = self._classify(top_score)

        logger.info(
            "confidence_assessed",
            level=level,
            top_score=round(top_score, 4),
            num_hits=len(hits),
        )
        return level

    def _classify(self, score: float) -> str:
        """Klassifiziert einen Score in eine Ampelstufe."""
        if score >= self._green:
            return GRUEN
        if score >= self._yellow:
            return GELB
        return ROT


def _best_score(hits: list[Any]) -> float:
    """Extrahiert den besten Score aus den Treffern.

    Bevorzugt rerank_score, faellt auf score zurueck.
    """
    scores: list[float] = []
    for hit in hits:
        rerank = getattr(hit, "rerank_score", None)
        if rerank is not None:
            scores.append(float(rerank))
        elif hasattr(hit, "score"):
            scores.append(float(hit.score))
    return max(scores) if scores else 0.0
