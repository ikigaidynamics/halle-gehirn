"""Post-Chunking-Filter fuer nicht-inhaltliche Chunks.

Entfernt Boilerplate, Front-Matter, Tail-Matter, Verzeichnisse und zu
kurze Chunks NACH dem Chunking, VOR Context-Enrichment und Embedding.

Filter-Regeln:
1. Mindestlaenge (MIN_CHUNK_CHARS) — Tabellen ausgenommen
2. Verzeichnis-Erkennung (Heading-Patterns)
3. Punktreihen-Heuristik (TOC ohne Heading)
4. Front-Matter-Filter (abschlussarbeit: alles vor erstem Kapitel-Heading)
   — Ausnahmen: Kurzfassung/Abstract sowie Tabellen-Chunks
5. Tail-Matter-Filter (abschlussarbeit: alles ab Anhang/Literaturverzeichnis)
   — Ausnahme: Tabellen-Chunks (positional bedeutungslos, s. _should_drop)
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
    # Erklaerungen / Eidesstattliche Versicherung (Abschlussarbeiten)
    "erklaerung",
    "erklärung",
    "eidesstattliche erklaerung",
    "eidesstattliche erklärung",
    "eidesstattliche versicherung",
    "selbstaendigkeitserklaerung",
    "selbständigkeitserklärung",
    "selbstständigkeitserklärung",
    "eigenstaendigkeitserklaerung",
    "eigenständigkeitserklärung",
})

# Tail-Matter-Headings: Ab diesem Heading werden ALLE nachfolgenden
# Chunks verworfen (inkl. Sub-Abschnitte).
# Nur fuer doc_type in (abschlussarbeit, promotion).
_TAIL_HEADINGS: frozenset[str] = frozenset({
    "anhang",
    "anhaenge",
    "anhänge",
    "appendix",
    "appendices",
    "literaturverzeichnis",
    "quellenverzeichnis",
    "references",
    "bibliography",
    "literatur",
    "quellen",
    "erklaerung",
    "erklärung",
    "eidesstattliche erklaerung",
    "eidesstattliche erklärung",
    "eidesstattliche versicherung",
    "selbstaendigkeitserklaerung",
    "selbständigkeitserklärung",
    "selbstständigkeitserklärung",
    "eigenstaendigkeitserklaerung",
    "eigenständigkeitserklärung",
})

# Kurzfassungs-/Abstract-Headings: inhaltstragende Front-Matter-Abschnitte,
# die den positionalen Front-Matter-Drop UEBERLEBEN (BTU-Abschlussarbeiten:
# Kurzfassung/Abstract stehen VOR "1 Einleitung", sind aber die dichteste
# Zusammenfassung der Arbeit). Nur unnummerierte Headings — ein nummeriertes
# "7 Zusammenfassung" ist regulaerer Inhalt und nie Front-Matter.
_ABSTRACT_HEADINGS: frozenset[str] = frozenset({
    "kurzfassung",
    "kurzzusammenfassung",
    "kurzreferat",
    "abstract",
    "zusammenfassung",
    "summary",
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

# Quellcode-Erkennung: typische Muster fuer Python/Java/C++
_CODE_LINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*(import\s+\w|from\s+\w+\s+import)"),
    re.compile(r"^\s*(def\s+\w+\s*\(|class\s+\w+[\s:(])"),
    re.compile(r"^\s*self\.\w+"),
    re.compile(r"^\s*(if\s+__name__\s*==|elif\s+|except\s+\w)"),
    re.compile(r"^\s*(return\s+\w|yield\s+|raise\s+\w)"),
    re.compile(
        r"^\s*(public|private|protected)\s+(static\s+)?"
        r"(void|int|String|boolean)",
    ),
    re.compile(r"^\s*#include\s*<"),
)
_CODE_DENSITY_THRESHOLD = 0.4
_CODE_MIN_LINES = 5


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
    5. Tail-Matter (nur abschlussarbeit) — alles ab Anhang /
       Literaturverzeichnis / Erklaerung.

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

    # Regel 4/5: Front- und Tail-Matter-Indizes bestimmen
    front_matter_end = _find_front_matter_end(chunks, doc_type)
    tail_matter_start = _find_tail_matter_start(chunks, doc_type)

    reasons: dict[str, int] = {}
    kept: list[Chunk] = []

    filter_code = s.filter_source_code

    for i, chunk in enumerate(chunks):
        reason = _should_drop(
            chunk, min_chars, i, front_matter_end, tail_matter_start,
            filter_code=filter_code,
        )
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


def _find_tail_matter_start(
    chunks: list[Chunk], doc_type: str,
) -> int:
    """Findet den Index des ersten Chunks mit Tail-Matter-Heading.

    Nur fuer doc_type in (abschlussarbeit, promotion). Alle Chunks
    AB diesem Index (inkl.) gelten als Tail-Matter und werden verworfen
    (Anhang, Literaturverzeichnis, Erklaerungen).

    Returns:
        Index des ersten Tail-Matter-Chunks, oder len(chunks).
    """
    if doc_type not in ("abschlussarbeit", "promotion"):
        return len(chunks)
    for i, chunk in enumerate(chunks):
        if _matches_tail_heading(chunk):
            return i
    return len(chunks)


def _matches_tail_heading(chunk: Chunk) -> bool:
    """Prueft ob ein Chunk ein Tail-Matter-Heading hat."""
    for heading in chunk.headings:
        normalized = _strip_section_number(heading.strip().lower())
        if normalized in _TAIL_HEADINGS:
            return True
    first_line = chunk.text.strip().split("\n")[0].strip().lower()
    first_line = re.sub(r"^#{1,6}\s+", "", first_line)
    first_line = _strip_section_number(first_line)
    return first_line in _TAIL_HEADINGS


def _matches_abstract_heading(chunk: Chunk) -> bool:
    """Prueft ob ein Chunk ein Kurzfassungs-/Abstract-Heading traegt.

    Bewusst OHNE Abschnittsnummern-Strip: nur unnummerierte Headings
    zaehlen — "Kurzfassung" ja, "7 Zusammenfassung" (Inhaltskapitel) nein.
    Prueft die gesamte Heading-Kette (top→leaf) und als Fallback die
    erste Textzeile.
    """
    for heading in chunk.headings:
        if heading.strip().lower() in _ABSTRACT_HEADINGS:
            return True
    first_line = chunk.text.strip().split("\n")[0].strip().lower()
    first_line = re.sub(r"^#{1,6}\s+", "", first_line)
    return first_line in _ABSTRACT_HEADINGS


def _should_drop(
    chunk: Chunk,
    min_chars: int,
    chunk_idx: int,
    front_matter_end: int,
    tail_matter_start: int,
    *,
    filter_code: bool = True,
) -> str | None:
    """Gibt den Verwurf-Grund zurueck oder None (behalten).

    Args:
        chunk: Der zu pruefende Chunk.
        min_chars: Mindestlaenge in Zeichen.
        chunk_idx: Position des Chunks in der Originalliste.
        front_matter_end: Index ab dem Inhalt beginnt.
        tail_matter_start: Index ab dem Tail-Matter beginnt.
        filter_code: Quellcode-Chunks herausfiltern.

    Returns:
        Grund-String oder None.
    """
    text = chunk.text.strip()

    # Regel 4/5 sind POSITIONAL — fuer Tabellen-Chunks bedeutungslos:
    # der Chunker haengt Tabellen ans Listenende (chunker.py), ihr Index
    # sagt nichts ueber ihre Dokumentposition. Ohne Positional-Ausnahme
    # wuerden ALLE Tabellen (auch Ergebnistabellen) als Tail-Matter fallen.
    # Trade-off: eine Tabelle, die tatsaechlich im Anhang steht, bleibt
    # dadurch im Index — verschmerzbar gegenueber dem Totalverlust.
    positional_exempt = chunk.is_table

    # Regel 4: Front-Matter (muss vor Regel 1, damit auch kurze
    # Front-Matter-Chunks den richtigen Grund bekommen).
    # Ausnahme: Kurzfassung/Abstract — inhaltstragend, bleibt im Index.
    if (
        front_matter_end > 0
        and chunk_idx < front_matter_end
        and not positional_exempt
        and not _matches_abstract_heading(chunk)
    ):
        return "front_matter"

    # Regel 5: Tail-Matter (Anhang, Literaturverzeichnis, Erklaerungen)
    if chunk_idx >= tail_matter_start and not positional_exempt:
        return "tail_matter"

    # Regel 1: Zu kurz (Tabellen ausgenommen)
    if len(text) < min_chars and not chunk.is_table:
        return "too_short"

    # Regel 2: Verzeichnis-Heading
    if _is_toc_chunk(chunk):
        return "toc_heading"

    # Regel 3: Punktreihen-Heuristik
    if _has_dot_leaders(text):
        return "dot_leaders"

    # Regel 6: Quellcode-Heuristik
    if filter_code and _is_source_code(text):
        return "source_code"

    return None


def _strip_section_number(heading: str) -> str:
    """Entfernt fuehrende Abschnittsnummern wie '7 ', '2.3 ', '1.2.1 '."""
    return re.sub(r"^\d+(\.\d+)*\.?\s+", "", heading)


def _is_toc_chunk(chunk: Chunk) -> bool:
    """Prueft ob der Chunk ein Verzeichnis-Abschnitt ist."""
    # Headings-Feld pruefen
    for heading in chunk.headings:
        normalized = _strip_section_number(heading.strip().lower())
        if normalized in _TOC_HEADINGS:
            return True
    # Erste Textzeile pruefen (fuer Chunks ohne headings-Feld)
    first_line = chunk.text.strip().split("\n")[0].strip().lower()
    first_line = re.sub(r"^#{1,6}\s+", "", first_line)
    first_line = _strip_section_number(first_line)
    return first_line in _TOC_HEADINGS


def _is_source_code(text: str) -> bool:
    """Erkennt Chunks die ueberwiegend Quellcode enthalten.

    Prueft ob ein signifikanter Anteil der Zeilen typische
    Quellcode-Muster matcht (import, def, class, self., etc.).

    Args:
        text: Chunk-Text.

    Returns:
        True wenn der Chunk als Quellcode erkannt wird.
    """
    lines = [line for line in text.split("\n") if line.strip()]
    if len(lines) < _CODE_MIN_LINES:
        return False
    code_lines = sum(
        1 for line in lines
        if any(p.match(line) for p in _CODE_LINE_PATTERNS)
    )
    return code_lines / len(lines) >= _CODE_DENSITY_THRESHOLD


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
