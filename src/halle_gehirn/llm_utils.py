"""Gemeinsame LLM-Hilfsfunktionen.

Zentrale Stelle fuer wiederkehrende LLM-Response-Verarbeitung.
Vermeidet Drift zwischen Kopien in reranker, context_enricher,
grounding, query_rewriter, query_transform.
"""
from __future__ import annotations

import re


def strip_think_tags(text: str) -> str:
    """Extrahiert die Antwort nach einem ``<think>``-Block (qwen3).

    Qwen3 gibt bei ``think=False`` trotzdem gelegentlich
    ``<think>...</think>Antwort`` aus. Diese Funktion extrahiert
    den sichtbaren Teil NACH dem Think-Block.

    Dreistufige Extraktion:
    1. Kein ``<think>`` → Text unveraendert (Fast-Path).
    2. Text nach ``</think>`` → Antwort.
    3. Fallback: Inhalt des ``<think>``-Blocks (nur Think, kein After).
    4. Letzter Fallback: leerer String.

    Args:
        text: Rohe LLM-Antwort.

    Returns:
        Bereinigter Antworttext.
    """
    if "<think>" not in text:
        return text.strip()
    # Antwort nach </think>
    match = re.search(r"</think>\s*(.*)", text, flags=re.DOTALL)
    if match and match.group(1).strip():
        return match.group(1).strip()
    # Fallback: Think-Inhalt
    inner = re.search(r"<think>(.*?)</think>", text, flags=re.DOTALL)
    if inner and inner.group(1).strip():
        return inner.group(1).strip()
    return ""
