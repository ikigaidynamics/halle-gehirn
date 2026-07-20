"""Zitations-Index aus Literaturverzeichnissen.

Parst ``Literaturverzeichnis``-Sektionen im Markdown-Body und extrahiert
nummerierte Referenzen als Lookup-Tabelle ``{ref_id: volltext}``. Der
Index wird als Dokument-Metadatum gespeichert, nicht als eigenstaendiger
Retrieval-Chunk — er dient der Zitations-Aufloesung wenn ein Nutzer
nach einer Inline-Referenz wie ``[6]`` fragt.
"""
from __future__ import annotations

import re

import structlog

logger = structlog.get_logger(__name__)

# Section-Headings, die ein Literaturverzeichnis einleiten
_BIB_HEADINGS: frozenset[str] = frozenset({
    "literaturverzeichnis",
    "quellenverzeichnis",
    "literatur",
    "quellen",
    "references",
    "bibliography",
    "quellenangaben",
    "literaturangaben",
})

# Heading-Pattern im Markdown
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# Nummerierter Eintrag: [1] Berger, K.: ...  oder  1. Berger, K.: ...
_NUMBERED_REF_RE = re.compile(
    r"^\[(\d+)\]\s+(.+)",
    re.MULTILINE,
)

# Alternative: "1. Autor" oder "(1) Autor"
_ALT_REF_RE = re.compile(
    r"^(?:(\d+)\.\s+|\((\d+)\)\s+)(.+)",
    re.MULTILINE,
)


def parse_citations(body_md: str) -> dict[str, str]:
    """Extrahiert Zitations-Eintraege aus dem Markdown-Body.

    Sucht die Literaturverzeichnis-Section und parst nummerierte
    Eintraege. Unterstuetzt ``[N] Text`` und ``N. Text`` Formate.
    Mehrzeilige Eintraege werden bis zum naechsten Eintrag akkumuliert.

    Args:
        body_md: Vollstaendiger Markdown-Body des Dokuments.

    Returns:
        Dict von Referenz-ID (String) → Volltext (leer wenn keine).
    """
    section = _find_bib_section(body_md)
    if section is None:
        return {}

    citations = _parse_bracket_refs(section)
    if not citations:
        citations = _parse_alt_refs(section)

    if citations:
        logger.info(
            "citations_extracted",
            entries=len(citations),
            sample=list(citations.keys())[:5],
        )
    return citations


def _find_bib_section(body_md: str) -> str | None:
    """Findet die Literaturverzeichnis-Section im Markdown."""
    headings = list(_HEADING_RE.finditer(body_md))
    for i, match in enumerate(headings):
        heading_text = match.group(2).strip().lower()
        heading_text = re.sub(r"^\d+(\.\d+)*\.?\s+", "", heading_text)
        if heading_text in _BIB_HEADINGS:
            start = match.end()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(body_md)
            return body_md[start:end]
    return None


def _parse_bracket_refs(section: str) -> dict[str, str]:
    """Parst [N]-Format-Referenzen mit Mehrzeilen-Akkumulation."""
    entries: dict[str, str] = {}
    matches = list(_NUMBERED_REF_RE.finditer(section))
    for i, match in enumerate(matches):
        ref_id = match.group(1)
        start = match.start(2)
        # Akkumuliere bis zum naechsten Eintrag
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section)
        text = section[start:end].strip()
        # Zeilenumbrueche zu Leerzeichen normalisieren
        text = " ".join(text.split())
        if text:
            entries[ref_id] = text
    return entries


def _parse_alt_refs(section: str) -> dict[str, str]:
    """Parst N. oder (N) Format-Referenzen."""
    entries: dict[str, str] = {}
    matches = list(_ALT_REF_RE.finditer(section))
    for i, match in enumerate(matches):
        ref_id = match.group(1) or match.group(2)
        text_start = match.start(3)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section)
        text = section[text_start:end].strip()
        text = " ".join(text.split())
        if text and ref_id:
            entries[ref_id] = text
    return entries
