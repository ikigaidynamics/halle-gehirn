"""Seiten-Provenienz: Zeichen-Offsets im Markdown → Seitennummern.

Docling exportiert Markdown als flachen String ohne Seiten-Info; die
Provenienz (``prov[0].page_no``) liegt aber an jedem Dokument-Element.
Dieses Modul baut daraus eine **Page-Map** ``[(char_offset, page_no), …]``
(aufsteigend sortiert), ueber die der Chunker jedem Body-Chunk seine
Seite zuordnet — Grundlage fuer „S. 42"-Zitate.

Pure Funktionen, kein Docling-Import — testbar ohne schwere Backends.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter

import structlog

logger = structlog.get_logger(__name__)

# Maximale Needle-Laenge fuer die Element-Suche im Markdown
_NEEDLE_CHARS = 80

# Eine Zeile muss so oft vorkommen, um als wiederholte Kopf-/Fusszeile
# ueber Seiten hinweg zu gelten
_REPEAT_THRESHOLD = 3

PageMap = list[tuple[int, int]]


def build_page_map(
    body_md: str,
    elements: list[tuple[str, int | None]],
) -> PageMap:
    """Baut eine Page-Map durch monotone Element-Suche im Markdown.

    Sucht jedes Element-Textfragment ab dem aktuellen Cursor im Body.
    Nicht auffindbare Elemente (Markdown-Escaping, Umformatierung)
    werden uebersprungen — die Map bleibt monoton und darf sparse sein.

    Args:
        body_md: Der (ggf. bereinigte) Markdown-Body.
        elements: ``(text, page_no)`` in Dokumentreihenfolge.

    Returns:
        Aufsteigend sortierte ``(char_offset, page_no)``-Liste; ein
        Eintrag pro Seitenwechsel.
    """
    page_map: PageMap = []
    cursor = 0
    last_page: int | None = None
    matched = 0

    for text, page in elements:
        if page is None:
            continue
        needle = " ".join(text.split())[:_NEEDLE_CHARS].strip()
        if not needle:
            continue
        idx = body_md.find(needle, cursor)
        if idx < 0:
            continue
        matched += 1
        cursor = idx + len(needle)
        if page != last_page:
            page_map.append((idx, page))
            last_page = page

    logger.debug(
        "page_map_built",
        elements=len(elements),
        matched=matched,
        page_entries=len(page_map),
    )
    return page_map


def page_for_offset(page_map: PageMap, offset: int) -> int | None:
    """Liefert die Seite fuer einen Zeichen-Offset.

    Args:
        page_map: Aufsteigend sortierte ``(offset, page)``-Liste.
        offset: Zeichen-Offset im Body-Markdown.

    Returns:
        Seitennummer des letzten Eintrags mit ``entry_offset <= offset``;
        vor dem ersten Eintrag die erste Seite; ``None`` bei leerer Map.
    """
    if not page_map:
        return None
    offsets = [entry[0] for entry in page_map]
    idx = bisect_right(offsets, offset) - 1
    if idx < 0:
        return page_map[0][1]
    return page_map[idx][1]


def join_pages_with_map(pages: list[str]) -> tuple[str, PageMap]:
    """Fuegt Seiten-Texte zusammen und liefert die exakte Page-Map.

    Fuer Backends mit Seiten-Granularitaet (pymupdf4llm ``page_chunks``).
    Leere Seiten werden uebersprungen, behalten aber ihre Original-Nummer.

    Args:
        pages: Markdown-Text je Seite (Index 0 = Seite 1).

    Returns:
        Tuple aus (Gesamt-Markdown, Page-Map).
    """
    parts: list[str] = []
    page_map: PageMap = []
    offset = 0
    for i, page_text in enumerate(pages, start=1):
        text = page_text.strip()
        if not text:
            continue
        page_map.append((offset, i))
        parts.append(text)
        offset += len(text) + 2  # "\n\n"-Joiner
    return "\n\n".join(parts), page_map


def remove_cross_page_repeats(pages: list[str]) -> list[str]:
    """Entfernt Zeilen, die ueber Seiten hinweg wiederholt vorkommen.

    Kopf-/Fusszeilen erscheinen einmal PRO Seite — eine seitenweise
    Bereinigung sieht sie daher nie oft genug. Diese Funktion zaehlt
    ueber alle Seiten und filtert je Seite.

    Args:
        pages: Markdown-Text je Seite.

    Returns:
        Seiten-Liste ohne wiederholte Kopf-/Fusszeilen.
    """
    counts: Counter[str] = Counter(
        line.strip()
        for page in pages
        for line in page.split("\n")
        if line.strip()
    )
    repeated = {
        line for line, count in counts.items()
        if count >= _REPEAT_THRESHOLD
    }
    if not repeated:
        return pages
    logger.debug(
        "cross_page_repeats_removed",
        patterns=[r[:60] for r in list(repeated)[:5]],
    )
    return [
        "\n".join(
            line for line in page.split("\n")
            if line.strip() not in repeated
        )
        for page in pages
    ]
