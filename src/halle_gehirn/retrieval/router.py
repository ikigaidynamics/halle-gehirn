"""Conditional Routing nach Query-Typ — Phase 4.

Klassifiziert Anfragen in Typen (factual/vergleich/definition/
temporal/overview) und ermoeglicht typspezifische Retrieval-Strategien.

Keyword-basiert (kein LLM-Aufruf) — deterministisch und schnell.
"""
from __future__ import annotations

import re

import structlog

from halle_gehirn.config import Settings, get_settings

logger = structlog.get_logger(__name__)

# Query-Typen
FACTUAL = "factual"
VERGLEICH = "vergleich"
DEFINITION = "definition"
TEMPORAL = "temporal"
OVERVIEW = "overview"

# Keyword-Muster fuer die Klassifikation (deutsch)
_PATTERNS: list[tuple[str, str]] = [
    # Vergleich
    (r"\b(vergleich|unterschied|differenz|gegenueber|versus|vs\.?)\b", VERGLEICH),
    (r"\b(besser|schlechter|vorteil|nachteil)", VERGLEICH),
    # Definition
    (r"\b(was\s+ist|was\s+sind|definition\b|bedeutet\b|bezeichn)", DEFINITION),
    (r"\b(erklaer|beschreib)", DEFINITION),
    # Temporal
    (r"\b(wann|seit\s+wann|ab\s+wann|bis\s+wann|zeitraum)\b", TEMPORAL),
    (r"\b(datum|termin|frist|deadline|jaehrlich|monatlich)\b", TEMPORAL),
    (r"\b(201\d|202\d|2030)\b", TEMPORAL),
    # Overview
    (r"\b(ueberblick|uebersicht|zusammenfass|aufzaehl|auflist)", OVERVIEW),
    (r"\b(welche\s+arten|welche\s+typen|alle\b.*\bliste)\b", OVERVIEW),
]

# Kompilierte Patterns (case-insensitive)
_COMPILED = [
    (re.compile(pattern, re.IGNORECASE), qtype)
    for pattern, qtype in _PATTERNS
]


class KeywordRouter:
    """Keyword-basierter Query-Router.

    Klassifiziert Anfragen deterministisch anhand von Keyword-Mustern.
    Kein LLM-Aufruf — schnell und vorhersagbar.

    Args:
        settings: Optionale Settings-Instanz.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def route(self, query: str) -> str:
        """Klassifiziert den Anfrage-Typ.

        Args:
            query: Die Benutzeranfrage.

        Returns:
            Query-Typ (factual/vergleich/definition/temporal/overview).
        """
        if not self._settings.use_router:
            return FACTUAL

        normalized = _normalize(query)
        for pattern, qtype in _COMPILED:
            if pattern.search(normalized):
                logger.debug(
                    "query_routed",
                    query_type=qtype,
                    query=query[:80],
                )
                return qtype

        logger.debug(
            "query_routed",
            query_type=FACTUAL,
            query=query[:80],
        )
        return FACTUAL


def _normalize(text: str) -> str:
    """Normalisiert Text fuer Pattern-Matching.

    Ersetzt deutsche Umlaute durch Doppelbuchstaben (ae/oe/ue)
    fuer konsistentes Matching, da Eingaben beides enthalten koennen.
    """
    replacements = {
        "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
        "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
    }
    for char, repl in replacements.items():
        text = text.replace(char, repl)
    return text
