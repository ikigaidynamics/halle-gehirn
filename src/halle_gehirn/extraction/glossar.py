"""Glossar-Extraktion aus Abkuerzungsverzeichnissen.

Parst ``Abkuerzungsverzeichnis``-Sektionen im Markdown-Body und extrahiert
AKRONYM → Langform-Paare. Das Glossar wird als Dokument-Metadatum
gespeichert und kann fuer Query-Expansion / Akronym-Aufloesung genutzt
werden, ohne selbst als Retrieval-Chunk zu erscheinen.
"""
from __future__ import annotations

import re

import structlog

logger = structlog.get_logger(__name__)

# Section-Headings, die ein Abkuerzungsverzeichnis einleiten
_GLOSSAR_HEADINGS: frozenset[str] = frozenset({
    "abkuerzungsverzeichnis",
    "abkürzungsverzeichnis",
    "abkuerzungen",
    "abkürzungen",
    "glossar",
    "glossary",
    "list of abbreviations",
    "abbreviations",
    "symbole und abkuerzungen",
    "symbole und abkürzungen",
    "symbolverzeichnis",
})

# Heading-Pattern im Markdown: ## Abkuerzungsverzeichnis
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# Eintrags-Pattern: AKRONYM — Langform (mit verschiedenen Trennzeichen)
# Beispiele:
#   AES — Advanced Encryption Standard
#   TCP - Tool Center Point
#   MRK - Mensch-Roboter-Kollaboration
#   ISO 9283    Leistungskenngroessen fuer Industrieroboter
_ENTRY_RE = re.compile(
    r"^([A-ZÄÖÜ][A-Za-zÄÖÜäöüß0-9./\- ]{0,30}?)"  # Akronym (Grossbuchstabe)
    r"\s*[—–\-:]\s*"                                    # Trennzeichen  # noqa: RUF001
    r"(.{3,}?)$",                                        # Langform (min. 3 Zeichen)
    re.MULTILINE,
)

# Tab-getrennte Eintraege (haeufig in LaTeX-generierten PDFs)
_TAB_ENTRY_RE = re.compile(
    r"^([A-ZÄÖÜ][A-Za-zÄÖÜäöüß0-9./\- ]{0,30}?)"
    r"\t+"
    r"(.{3,}?)$",
    re.MULTILINE,
)


def parse_glossar(body_md: str) -> dict[str, str]:
    """Extrahiert Abkuerzungen aus dem Markdown-Body.

    Sucht die Abkuerzungsverzeichnis-Section, parst AKRONYM — Langform
    Paare und gibt sie als dict zurueck.

    Args:
        body_md: Vollstaendiger Markdown-Body des Dokuments.

    Returns:
        Dict von Abkuerzung → Langform (leer wenn keine gefunden).
    """
    section = _find_glossar_section(body_md)
    if section is None:
        return {}

    glossar: dict[str, str] = {}

    # Beide Formate versuchen
    for match in _ENTRY_RE.finditer(section):
        key = match.group(1).strip()
        value = match.group(2).strip()
        if key and value and len(key) <= 30:
            glossar[key] = value

    # Tab-getrennte Eintraege (ergaenzend)
    for match in _TAB_ENTRY_RE.finditer(section):
        key = match.group(1).strip()
        value = match.group(2).strip()
        if key and value and key not in glossar and len(key) <= 30:
            glossar[key] = value

    if glossar:
        logger.info(
            "glossar_extracted",
            entries=len(glossar),
            sample=list(glossar.keys())[:5],
        )
    return glossar


def _find_glossar_section(body_md: str) -> str | None:
    """Findet die Abkuerzungsverzeichnis-Section im Markdown.

    Returns:
        Der Text der Section oder None.
    """
    headings = list(_HEADING_RE.finditer(body_md))
    for i, match in enumerate(headings):
        heading_text = match.group(2).strip().lower()
        # Abschnittsnummern entfernen: "3 Abkuerzungsverzeichnis" → "abkuerzungsverzeichnis"
        heading_text = re.sub(r"^\d+(\.\d+)*\.?\s+", "", heading_text)
        if heading_text in _GLOSSAR_HEADINGS:
            start = match.end()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(body_md)
            return body_md[start:end]
    return None
