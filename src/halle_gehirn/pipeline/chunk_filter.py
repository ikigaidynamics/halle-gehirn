"""Post-Chunking-Filter fuer nicht-inhaltliche Chunks.

Entfernt Boilerplate, Front-Matter, Verzeichnisse und zu kurze Chunks
NACH dem Chunking, VOR Context-Enrichment und Embedding.

Filter-Regeln:
1. Mindestlaenge (MIN_CHUNK_CHARS)
2. Verzeichnis-Erkennung (Heading-Patterns)
3. Punktreihen-Heuristik (TOC ohne Heading)
4. Front-Matter-Filter (abschlussarbeit: alles vor erstem Kapitel-Heading)
"""
from __future__ import annotations

import re

import structlog

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.pipeline.chunker import Chunk

logger = structlog.get_logger(__name__)

# Verzeichnis-Headings (case-insensitive, nach Strip von #-Markern)
_TOC_HEADINGS: frozenset[str] = frozenset({
    "inhaltsverzeichnis",
    "inhaltverzeichnis",
    "abbildungsverzeichnis",
    "tabellenverzeichnis",
    "abkuerzungsverzeichnis",
    "abkürzungsverzeichnis",
    "literaturverzeichnis",
    "quellenverzeichnis",
    "anhang",
    "table of contents",
    "list of figures",
    "list of tables",
    "references",
    "bibliography",
})

# Punktreihen: "Kapitelname ......... 12"
_DOT_LEADER_RE = re.compile(r"\.{3,}\s*\d+")

# Nummeriertes Kapitel-Heading: "## 1 Einleitung", "### 2.1 Wartung", "# 1. Foo"
_NUMBERED_HEADING_RE = re.compile(
    r"^#{1,6}\s+\d+(\.\d*)*\.?\s+\w", re.MULTILINE,
)

# Nummeriertes Heading auf bereits normalisiertem Text (ohne #-Praefix, ohne Bold)
_NUMBERED_HEADING_BARE_RE = re.compile(
    r"^\d+(\.\d*)*\.?\s+\w",
)


def filter_chunks(
    chunks: list[Chunk],
    doc_type: str = "",
    settings: Settings | None = None,
) -> list[Chunk]:
    """Filtert nicht-inhaltliche Chunks heraus.

    Wendet in Reihenfolge an:
    1. MIN_CHUNK_CHARS — zu kurze Chunks verwerfen.
    2. Verzeichnis-Erkennung an Heading/Breadcrumb.
    3. Punktreihen-Heuristik.
    4. Front-Matter (nur abschlussarbeit) — alles vor erstem
       nummerierten Kapitel-Heading.

    Args:
        chunks: Chunks vom Chunker.
        doc_type: Dokumenttyp (z.B. "abschlussarbeit").
        settings: Optionale Settings fuer min_chunk_chars.

    Returns:
        Gefilterte Liste, chunk_index neu vergeben.
    """
    s = settings or get_settings()
    min_chars = s.min_chunk_chars
    original_count = len(chunks)

    # Regel 4: Front-Matter-Index bestimmen (vor den Einzelfiltern)
    front_matter_end = _find_front_matter_end(chunks, doc_type)

    reasons: dict[str, int] = {}
    kept: list[Chunk] = []

    for i, chunk in enumerate(chunks):
        reason = _should_drop(chunk, min_chars, i, front_matter_end)
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
        else:
            kept.append(chunk)

    # Re-Indizierung
    for idx, chunk in enumerate(kept):
        chunk.chunk_index = idx

    dropped = original_count - len(kept)
    if dropped > 0:
        logger.info(
            "chunks_filtered",
            original=original_count,
            kept=len(kept),
            dropped=dropped,
            reasons=reasons,
        )
    return kept


def _find_front_matter_end(
    chunks: list[Chunk], doc_type: str,
) -> int:
    """Findet den Index des ersten Chunks mit nummeriertem Heading.

    Nur fuer doc_type in (abschlussarbeit, promotion). Alle Chunks
    VOR diesem Index gelten als Front-Matter.

    Prueft die *normalisierten* Headings (ohne Markdown-Inline-Formatierung),
    nicht den rohen chunk.text — so funktioniert die Erkennung unabhaengig
    davon welches Extraction-Backend (Docling, pymupdf4llm, …) die
    Headings erzeugt hat.

    Returns:
        Index des ersten Kapitel-Chunks, oder 0 (kein Front-Matter).
    """
    if doc_type not in ("abschlussarbeit", "promotion"):
        return 0
    for i, chunk in enumerate(chunks):
        # Normalisierte Headings pruefen (Bold/Italic bereits entfernt)
        for heading in chunk.headings:
            if _NUMBERED_HEADING_BARE_RE.match(heading):
                return i
        # Fallback: Rohtext (fuer Chunks ohne headings-Feld)
        if _NUMBERED_HEADING_RE.search(chunk.text):
            return i
    # Kein nummeriertes Heading → Fallback: nichts verwerfen
    return 0


def _should_drop(
    chunk: Chunk,
    min_chars: int,
    chunk_idx: int,
    front_matter_end: int,
) -> str | None:
    """Gibt den Verwurf-Grund zurueck oder None (behalten).

    Args:
        chunk: Der zu pruefende Chunk.
        min_chars: Mindestlaenge in Zeichen.
        chunk_idx: Position des Chunks in der Originalliste.
        front_matter_end: Index ab dem Inhalt beginnt.

    Returns:
        Grund-String oder None.
    """
    text = chunk.text.strip()

    # Regel 4: Front-Matter (muss vor Regel 1, damit auch kurze
    # Front-Matter-Chunks den richtigen Grund bekommen)
    if front_matter_end > 0 and chunk_idx < front_matter_end:
        return "front_matter"

    # Regel 1: Zu kurz (Tabellen ausgenommen)
    if len(text) < min_chars and not chunk.is_table:
        return "too_short"

    # Regel 2: Verzeichnis-Heading
    if _is_toc_chunk(chunk):
        return "toc_heading"

    # Regel 3: Punktreihen-Heuristik
    if _has_dot_leaders(text):
        return "dot_leaders"

    return None


def _is_toc_chunk(chunk: Chunk) -> bool:
    """Prueft ob der Chunk ein Verzeichnis-Abschnitt ist."""
    # Headings-Feld pruefen
    for heading in chunk.headings:
        if heading.strip().lower() in _TOC_HEADINGS:
            return True
    # Erste Textzeile pruefen (fuer Chunks ohne headings-Feld)
    first_line = chunk.text.strip().split("\n")[0].strip().lower()
    first_line = re.sub(r"^#{1,6}\s+", "", first_line)
    return first_line in _TOC_HEADINGS


def _has_dot_leaders(text: str) -> bool:
    """Erkennt TOC-artigen Inhalt mit Fuellpunkten.

    Gibt True zurueck wenn >50% der nicht-leeren Zeilen das
    Punktreihen-Pattern matchen (mindestens 3 Zeilen).
    """
    lines = [line for line in text.split("\n") if line.strip()]
    if len(lines) < 3:
        return False
    dot_lines = sum(1 for line in lines if _DOT_LEADER_RE.search(line))
    return dot_lines / len(lines) > 0.5
