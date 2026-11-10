"""Regex-Smalltalk-Detection (0 ms) -- Phase 5.

Erkennt Smalltalk-Anfragen (Begruessung, Identity, Capability, Abschied)
und antwortet Persona-konsistent OHNE LLM-Call. Patterns auf Deutsch.
"""
from __future__ import annotations

import re

import structlog

logger = structlog.get_logger(__name__)

# Kategorien: (compiled_pattern, category_key)
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Begruessung
    (re.compile(
        r"^\s*(hallo|hi|hey|moin|guten\s*(morgen|tag|abend)|servus|grüß\s*gott)\s*[!.?]?\s*$",
        re.IGNORECASE,
    ), "greeting"),
    # Identity
    (re.compile(
        r"(wer\s+bist\s+du|wie\s+hei(ss|ß)(t|en)\s+(du|sie)|dein\s+name)",
        re.IGNORECASE,
    ), "identity"),
    # Capability
    (re.compile(
        r"(was\s+kannst\s+du|was\s+k(ö|oe)nnen\s+sie|wozu\s+bist\s+du|"
        r"was\s+sind\s+deine\s+f(ä|ae)higkeiten|hilfe|help\b)",
        re.IGNORECASE,
    ), "capability"),
    # Abschied
    (re.compile(
        r"^\s*(tsch(ü|ue)ss?|auf\s*wiedersehen|bye|ciao|bis\s+(bald|dann|sp(ä|ae)ter))\s*[!.?]?\s*$",
        re.IGNORECASE,
    ), "farewell"),
    # Danke
    (re.compile(
        r"^\s*(danke|vielen\s+dank|dank\s+dir|merci)\s*[!.?]?\s*$",
        re.IGNORECASE,
    ), "thanks"),
]

# Antworten je Kategorie (Persona KI Fabrik Scout: sachlich, freundlich)
_RESPONSES: dict[str, str] = {
    "greeting": (
        "Hallo! Ich bin KI Fabrik Scout, der KI-Assistent des Lehrstuhls fuer"
        "KI-gestuetzte Automatisierungstechnik. Wie kann ich Ihnen helfen?"
    ),
    "identity": (
        "Ich bin KI Fabrik Scout, der Wissensassistent des Lehrstuhls fuer"
        "KI-gestuetzte Automatisierungstechnik an der BTU Cottbus-Senftenberg. "
        "Ich beantworte Fragen auf Basis der dokumentierten Lehrstuhl-Wissensbasis."
    ),
    "capability": (
        "Ich kann Fragen zur Modellfabrik, den Anlagen, Forschungsprojekten, "
        "Abschlussarbeiten und der Lehre am Lehrstuhl beantworten -- "
        "immer auf Basis belegter Quellen. Stellen Sie mir gerne eine Frage."
    ),
    "farewell": "Auf Wiedersehen! Bei weiteren Fragen stehe ich gerne zur Verfuegung.",
    "thanks": "Gerne! Wenn Sie weitere Fragen haben, stehe ich bereit.",
}


def is_smalltalk(query: str) -> bool:
    """Prueft ob die Anfrage Smalltalk ist (kein Retrieval noetig).

    Args:
        query: Die Benutzeranfrage.

    Returns:
        True wenn Smalltalk erkannt, sonst False.
    """
    return any(pattern.search(query) for pattern, _ in _PATTERNS)


def get_response(query: str) -> str:
    """Liefert eine Persona-konsistente Smalltalk-Antwort.

    Args:
        query: Die Benutzeranfrage (muss Smalltalk sein).

    Returns:
        Antwort-String. Fallback auf Begruessung bei unbekannter Kategorie.
    """
    for pattern, category in _PATTERNS:
        if pattern.search(query):
            logger.debug("smalltalk_detected", category=category)
            return _RESPONSES[category]
    return _RESPONSES["greeting"]
