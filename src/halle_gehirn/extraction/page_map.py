"""Seiten-Provenienz: Zeichen-Offsets im Markdown → Seitennummern.

Docling exportiert Markdown als flachen String ohne Seiten-Info; die
Provenienz (``prov[0].page_no``) liegt aber an jedem Dokument-Element.
Dieses Modul baut daraus eine **Page-Map** ``[(char_offset, page_no), …]``
(aufsteigend sortiert), ueber die der Chunker jedem Body-Chunk seine
Seite zuordnet — Grundlage fuer „S. 42"-Zitate.

Pure Funktionen, kein Docling-Import — testbar ohne schwere Backends.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from collections import Counter
from collections.abc import Callable

import structlog

logger = structlog.get_logger(__name__)

# Maximale Needle-Laenge fuer die Element-Suche im Markdown
_NEEDLE_CHARS = 80

# Kuerzere Needle-Laengen als Fallback bei fehlgeschlagener Suche
_FALLBACK_NEEDLE_CHARS = (50, 30)

# Eine Zeile muss so oft vorkommen, um als wiederholte Kopf-/Fusszeile
# ueber Seiten hinweg zu gelten
_REPEAT_THRESHOLD = 3

PageMap = list[tuple[int, int]]

# Marker, den Docling Serve zwischen Seiten einfuegt
PAGE_BREAK_MARKER = "<!-- PAGE_BREAK -->"


def build_page_map(
    body_md: str,
    elements: list[tuple[str, int | None]],
    *,
    normalize: Callable[[str], str] | None = None,
) -> PageMap:
    """Baut eine Page-Map durch monotone Element-Suche im Markdown.

    Sucht jedes Element-Textfragment ab dem aktuellen Cursor im Body.
    Nicht auffindbare Elemente (Markdown-Escaping, Umformatierung)
    werden uebersprungen — die Map bleibt monoton und darf sparse sein.

    Bei Nicht-Treffer wird mit kuerzeren Needles (50, 30 Zeichen)
    erneut gesucht, um Treffer trotz Formatierungsdifferenzen zu
    ermoeglichen.

    Args:
        body_md: Der (ggf. bereinigte) Markdown-Body.
        elements: ``(text, page_no)`` in Dokumentreihenfolge.
        normalize: Optionale Funktion zur Needle-Normalisierung.
            Sollte dieselben Inline-Transformationen anwenden wie
            die Boilerplate-Bereinigung des Body (z.B. Zitations-
            Entfernung), damit Needle und Body uebereinstimmen.

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
        raw = " ".join(text.split())
        if normalize:
            raw = " ".join(normalize(raw).split())
        if not raw:
            continue
        needle = raw[:_NEEDLE_CHARS].strip()
        if not needle:
            continue
        idx = body_md.find(needle, cursor)
        # Fallback: kuerzere Needles bei Nicht-Treffer
        if idx < 0:
            for shorter in _FALLBACK_NEEDLE_CHARS:
                fallback_needle = raw[:shorter].strip()
                if not fallback_needle or fallback_needle == needle:
                    continue
                idx = body_md.find(fallback_needle, cursor)
                if idx >= 0:
                    needle = fallback_needle
                    break
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


def strip_page_markers(body_md: str) -> tuple[str, PageMap]:
    """Extrahiert Page-Map aus eingebetteten Seitenumbruch-Markern.

    Docling Serve fuegt ``<!-- PAGE_BREAK -->`` zwischen Seiten ein,
    wenn ``md_page_break_placeholder`` gesetzt ist. Diese Funktion
    entfernt die Marker und baut daraus eine exakte Page-Map.

    Vorteil gegenueber ``build_page_map``: keine Needle-Suche noetig,
    100 % Trefferquote, unabhaengig von Boilerplate-Cleaning.

    Args:
        body_md: Markdown-Body MIT eingebetteten Seitenumbruch-Markern.

    Returns:
        Tuple aus (bereinigter Body ohne Marker, exakte Page-Map).
    """
    marker = PAGE_BREAK_MARKER
    if marker not in body_md:
        return body_md, []

    page_map: PageMap = [(0, 1)]
    page = 1
    cleaned_parts: list[str] = []
    offset = 0

    for segment in body_md.split(marker):
        cleaned_parts.append(segment)
        offset += len(segment)
        page += 1
        page_map.append((offset, page))

    # Letzter Eintrag nach dem letzten Segment ist ueberfluessig
    page_map.pop()

    result = "".join(cleaned_parts)
    logger.debug(
        "page_map_from_markers",
        pages=len(page_map),
        body_chars=len(result),
    )
    return result, page_map


def strip_markers_and_clean(
    body_md: str,
    clean_fn: Callable[[str], str] | None = None,
) -> tuple[str, PageMap]:
    """Entfernt Seitenumbruch-Marker UND bereinigt in einem Schritt.

    Ersetzt die alte Kombination ``strip_page_markers()`` +
    ``adjust_page_map()``, die Seiteneinträge verlor weil ihre
    Needle-Suche nach dem Cleaning regelmäßig scheiterte (Seiten-
    anfänge bestehen oft aus genau dem Boilerplate, das entfernt wird).

    Lösung: Unsichtbare Sentinel-Zeichen (``\\x01``) an jeder
    Seitengrenze einfügen, **dann** die Cleaning-Funktion auf den
    Gesamttext anwenden (repeated-header-Erkennung sieht alle Seiten),
    **dann** die Sentinels extrahieren und entfernen. Ergebnis: 100 %
    exakte Page-Map unabhängig davon was das Cleaning entfernt.

    Args:
        body_md: Markdown-Body MIT ``<!-- PAGE_BREAK -->``-Markern.
        clean_fn: Optionale Bereinigungsfunktion (z.B. ``boilerplate.clean``).
            Wird auf den Gesamttext angewendet.

    Returns:
        Tuple aus (bereinigter Body, exakte Page-Map).
    """
    marker = PAGE_BREAK_MARKER
    if marker not in body_md:
        cleaned = clean_fn(body_md) if clean_fn else body_md
        return cleaned, []

    segments = body_md.split(marker)

    if clean_fn is None:
        # Kein Cleaning — direkt zusammenfügen + Page-Map bauen
        page_map: PageMap = []
        offset = 0
        for i, seg in enumerate(segments, start=1):
            page_map.append((offset, i))
            offset += len(seg)
        return "".join(segments), page_map

    # Sentinels an Seitengrenzen einfügen.  \x01 (SOH) wird von keinem
    # Boilerplate-Regex erkannt (die matchen nur druckbare Zeichen).
    _SENTINEL_FMT = "\x01PG{}\x01"
    parts: list[str] = []
    for i, seg in enumerate(segments):
        if i > 0:
            parts.append(_SENTINEL_FMT.format(i + 1))
        parts.append(seg)
    marked_body = "".join(parts)

    # Cleaning auf den vollen Text anwenden
    cleaned = clean_fn(marked_body)

    # Sentinels extrahieren, Positionen merken, dann entfernen
    sentinel_re = re.compile(r"\x01PG(\d+)\x01")
    page_map = [(0, 1)]

    matches = list(sentinel_re.finditer(cleaned))
    if not matches:
        # Alle Sentinels verloren (sollte nicht passieren) — Fallback
        logger.warning(
            "page_sentinels_lost",
            segments=len(segments),
        )
        return cleaned, page_map

    result_parts: list[str] = []
    removed_chars = 0
    last_end = 0
    for m in matches:
        result_parts.append(cleaned[last_end:m.start()])
        adj_pos = m.start() - removed_chars
        page_num = int(m.group(1))
        page_map.append((adj_pos, page_num))
        removed_chars += len(m.group())
        last_end = m.end()
    result_parts.append(cleaned[last_end:])

    final_body = "".join(result_parts)
    logger.debug(
        "page_map_from_sentinels",
        pages=len(page_map),
        body_chars=len(final_body),
    )
    return final_body, page_map


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
