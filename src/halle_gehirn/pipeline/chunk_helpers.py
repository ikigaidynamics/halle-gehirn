"""Hilfstypen und -funktionen fuer den Chunker.

Enthaelt Section-Splitting (Markdown an Headings zerlegen),
hierarchisches Section-Merging (Geschwister-Sektionen unter gleichem
Eltern-Heading zusammenfassen) und Tabellen-Splitting (uebergrosse
Markdown-Tabellen an Zeilengrenzen teilen, Header wird in jedem Teil
wiederholt).
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)

# Heading-Pattern: ## Heading oder ### Heading etc.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# Inline-Markdown-Formatierung (Bold, Italic, Code, Underline)
_INLINE_MD_RE = re.compile(r"(\*{1,2}|_{1,2}|`)")


def normalize_heading(raw: str) -> str:
    """Normalisiert Heading-Text von verschiedenen Extractoren.

    Entfernt Markdown-Inline-Formatierung (``**bold**``, ``*italic*``,
    `` `code` ``, ``__underline__``) und normalisiert Whitespace.
    Verschiedene Backends (Docling, pymupdf4llm, kuenftige) erzeugen
    unterschiedliches Markdown — eine Normalisierungsstelle ist robust.

    Args:
        raw: Roher Heading-Text (ohne ``#``-Praefix).

    Returns:
        Bereinigter Heading-Text.
    """
    cleaned = _INLINE_MD_RE.sub("", raw)
    return " ".join(cleaned.split()).strip()

# Separator-Zeile einer Markdown-Tabelle: |---|...|
_TABLE_SEP_RE = re.compile(r"^\s*\|[\s\-:|]+\|")


# ── Section-Splitting ──


@dataclass
class Section:
    """Ein Abschnitt im Markdown (Heading + zugehoeriger Text)."""

    text: str
    start: int
    headings: list[str] = field(default_factory=list)


def split_sections(body: str) -> list[Section]:
    """Teilt Markdown-Body an Headings in Sections auf.

    ``Section.headings`` enthaelt die vollstaendige Heading-Kette von der
    obersten Ebene bis zum eigenen Heading (top → leaf), abgeleitet aus den
    ``#``-Leveln — z. B. ``["Masterarbeit", "2 Grundlagen", "2.1 Kinematik"]``.
    Das eigene Heading einer Section ist immer ``headings[-1]``.

    Args:
        body: Markdown-Text.

    Returns:
        Liste von Sections mit Text-Offsets und Heading-Ketten.
    """
    if not body.strip():
        return []
    heading_matches = list(_HEADING_RE.finditer(body))
    if not heading_matches:
        return [Section(text=body, start=0)]

    sections: list[Section] = []
    # Text vor erstem Heading
    if heading_matches[0].start() > 0:
        pre = body[: heading_matches[0].start()]
        if pre.strip():
            sections.append(Section(text=pre, start=0))

    # Heading-Stack: (level, text) — haelt die aktuelle Eltern-Kette
    heading_stack: list[tuple[int, str]] = []
    for i, match in enumerate(heading_matches):
        level = len(match.group(1))
        heading_text = normalize_heading(match.group(2))
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, heading_text))

        start = match.start()
        end = (
            heading_matches[i + 1].start()
            if i + 1 < len(heading_matches)
            else len(body)
        )
        section_text = body[start:end]
        sections.append(Section(
            text=section_text,
            start=start,
            headings=[text for _, text in heading_stack],
        ))
    return sections


# ── Hierarchisches Section-Merging ──

# Strukturelle Headings, die nie zusammengefasst werden duerfen (Verzeichnisse,
# Anhang, Erklaerungen, Kurzfassung/Abstract). Chunk-Filter verlassen sich
# darauf, dass diese als eigene Chunks sichtbar bleiben (Verzeichnis-Drop,
# Tail-Matter-Drop, Abstract-Whitelist). Lowercase, ohne Abschnittsnummer.
_UNMERGEABLE_HEADINGS: frozenset[str] = frozenset({
    # Verzeichnisse
    "inhaltsverzeichnis", "inhaltverzeichnis",
    "abbildungsverzeichnis", "tabellenverzeichnis",
    "abkuerzungsverzeichnis", "abkürzungsverzeichnis",
    "literaturverzeichnis", "quellenverzeichnis",
    # Tail-Matter
    "anhang", "anhaenge", "anhänge",
    "appendix", "appendices",
    "literatur", "quellen",
    "erklaerung", "erklärung",
    "eidesstattliche erklaerung", "eidesstattliche erklärung",
    "eidesstattliche versicherung",
    "selbstaendigkeitserklaerung", "selbständigkeitserklärung",
    "selbstständigkeitserklärung",
    "eigenstaendigkeitserklaerung", "eigenständigkeitserklärung",
    # EN-Varianten
    "table of contents", "list of figures", "list of tables",
    "references", "bibliography",
    # Kurzfassung/Abstract: vom Front-Matter-Filter als Ausnahme behandelt,
    # muss als eigener Chunk erkennbar bleiben
    "kurzfassung", "kurzzusammenfassung", "kurzreferat",
    "abstract", "zusammenfassung", "summary",
})

# Nummeriertes Heading: "2 Grundlagen", "2.1 Kinematik", "1. Einleitung"
_NUM_PREFIX_RE = re.compile(r"^\d+(\.\d+)*\.?\s+")


def merge_sibling_sections(
    sections: list[Section],
    target_tokens: int,
    count_tokens_fn: Callable[[str], int],
) -> list[Section]:
    """Fasst aufeinanderfolgende Geschwister-Sektionen zusammen.

    Zwei Sektionen werden zusammengefasst, wenn:
    - sie denselben Eltern-Heading-Pfad teilen (``headings[:-1]`` identisch)
      ODER die zweite ein direktes Kind der ersten ist (Headings der ersten
      sind Praefix der zweiten), UND
    - die kombinierte Token-Anzahl <= *target_tokens* ist, UND
    - keine der beiden Sektionen ein strukturelles Heading hat (Verzeichnisse,
      Anhang, Erklaerungen) — diese muessen fuer den Chunk-Filter als eigene
      Chunks sichtbar bleiben.

    Greedy, single-pass: Der Akkumulator waechst, bis die naechste Sektion
    nicht mehr passt. Sektionen OHNE Headings (Text vor dem ersten Heading)
    werden nie zusammengefasst.

    Args:
        sections: Sektionen aus ``split_sections()``.
        target_tokens: Soft-Obergrenze fuer zusammengefasste Sektionen.
        count_tokens_fn: Token-Zaehlfunktion.

    Returns:
        Neue Liste (keine Mutation der Eingabe).
    """
    if len(sections) <= 1:
        return list(sections)

    merged: list[Section] = [sections[0]]
    merges = 0

    for nxt in sections[1:]:
        cur = merged[-1]
        if (
            cur.headings
            and nxt.headings
            and _can_merge(cur, nxt)
            and count_tokens_fn(cur.text + "\n\n" + nxt.text) <= target_tokens
        ):
            # Zusammenfassen: Text verketten, Headings des Akkumulators behalten
            merged[-1] = Section(
                text=cur.text + "\n\n" + nxt.text,
                start=cur.start,
                headings=cur.headings,
            )
            merges += 1
        else:
            merged.append(nxt)

    if merges:
        logger.info(
            "sections_merged",
            original=len(sections),
            merged=len(merged),
            merges=merges,
        )
    return merged


def _is_unmergeable(section: Section) -> bool:
    """Prueft ob eine Sektion ein strukturelles Heading hat."""
    if not section.headings:
        return False
    leaf = section.headings[-1].strip().lower()
    leaf = _NUM_PREFIX_RE.sub("", leaf)
    return leaf in _UNMERGEABLE_HEADINGS


def _can_merge(a: Section, b: Section) -> bool:
    """Prueft ob zwei Sektionen zusammenfassbar sind (Heading-Relation)."""
    # Strukturelle Headings nie zusammenfassen
    if _is_unmergeable(a) or _is_unmergeable(b):
        return False
    parent_a = a.headings[:-1]
    parent_b = b.headings[:-1]
    # Fall 1: Geschwister (gleicher Eltern-Pfad)
    if parent_a == parent_b:
        return True
    # Fall 2: b ist direktes Kind von a (a.headings ist Praefix von b.headings)
    return b.headings[: len(a.headings)] == a.headings


# ── Tabellen-Splitting ──


def split_table(
    table_md: str,
    max_tokens: int,
    page: int | None,
    count_tokens_fn: Callable[[str], int],
) -> list[dict[str, object]]:
    """Teilt eine uebergrosse Markdown-Tabelle an Zeilengrenzen.

    Der Header (inkl. Separator-Zeile) wird in jedem Teil wiederholt.
    Passt die Tabelle in *max_tokens*, wird ein einzelnes Ergebnis
    zurueckgegeben.

    Args:
        table_md: Vollstaendiger Markdown-Tabellen-Text.
        max_tokens: Maximale Tokens pro Chunk.
        page: Optionale Seitenzahl.
        count_tokens_fn: Callable(str) -> int fuer Token-Zaehlung.

    Returns:
        Liste von Dicts mit Feldern ``text``, ``page``, ``is_table``.
    """
    ct = count_tokens_fn
    text = table_md.strip()

    # Gesamte Tabelle pruefen
    if ct(text) <= max_tokens:
        return [{"text": text, "page": page, "is_table": True}]

    lines = text.split("\n")

    # Header finden: Zeilen vor der Separator-Zeile
    sep_idx = _find_separator(lines)
    if sep_idx is None or sep_idx == 0:
        # Kein valider Markdown-Table-Header → atomar zurueckgeben
        return [{"text": text, "page": page, "is_table": True}]

    header_lines = lines[: sep_idx + 1]
    data_lines = lines[sep_idx + 1 :]
    header_text = "\n".join(header_lines)
    header_tokens: int = ct(header_text)

    if not data_lines:
        return [{"text": text, "page": page, "is_table": True}]

    parts: list[dict[str, object]] = []
    buf: list[str] = []
    buf_tokens = 0

    for row in data_lines:
        row_tokens: int = ct(row)
        if buf and header_tokens + buf_tokens + row_tokens > max_tokens:
            chunk_text = header_text + "\n" + "\n".join(buf)
            parts.append({
                "text": chunk_text, "page": page, "is_table": True,
            })
            buf = []
            buf_tokens = 0
        buf.append(row)
        buf_tokens += row_tokens

    if buf:
        chunk_text = header_text + "\n" + "\n".join(buf)
        parts.append({
            "text": chunk_text, "page": page, "is_table": True,
        })

    logger.debug(
        "table_split",
        original_tokens=ct(text),
        sub_chunks=len(parts),
    )
    return parts


def _find_separator(lines: list[str]) -> int | None:
    """Findet den Index der Separator-Zeile (|---|...|)."""
    for i, line in enumerate(lines):
        if _TABLE_SEP_RE.match(line):
            return i
    return None


# ── Harter Text-Split (Zeilen → Woerter → Token) ──


@dataclass
class TextSpan:
    """Ergebnis eines harten Text-Splits (text + Offsets)."""

    text: str
    start: int
    end: int


def hard_split_text(
    text: str,
    max_tokens: int,
    offset: int,
    count_tokens_fn: Callable[[str], int],
    encode_fn: Callable[[str], list[int]],
    decode_fn: Callable[[list[int]], str],
) -> list[TextSpan]:
    """Teilt Text an Zeilen-, Wort-, notfalls Token-Grenzen.

    Letzter Ausweg wenn weder Heading- noch Satz-Split greifen.
    Garantiert: jeder Span <= max_tokens.

    Args:
        text: Zu teilender Text.
        max_tokens: Hartes Token-Limit.
        offset: Zeichen-Offset im Quelldokument.
        count_tokens_fn: Token-Zaehlfunktion.
        encode_fn: Text → Token-IDs.
        decode_fn: Token-IDs → Text.
    """
    if not text.strip() or count_tokens_fn(text) <= max_tokens:
        return [TextSpan(text=text, start=offset, end=offset + len(text))]

    # Atomare Einheiten: Zeilen (bevorzugt), sonst Woerter
    joiner = "\n" if "\n" in text else " "
    atoms = text.split(joiner)

    # Atome die einzeln > max: an Token-Grenzen teilen
    safe: list[str] = []
    for atom in atoms:
        if count_tokens_fn(atom) <= max_tokens:
            safe.append(atom)
        else:
            tokens = encode_fn(atom)
            for i in range(0, len(tokens), max_tokens):
                safe.append(decode_fn(tokens[i : i + max_tokens]))

    # Greedy-Akkumulation (joiner-Token-Overhead beruecksichtigen)
    joiner_tok = count_tokens_fn(joiner)
    spans: list[TextSpan] = []
    buf: list[str] = []
    buf_tokens = 0  # Tokens inkl. Joiner-Overhead
    pos = offset

    for part in safe:
        pt = count_tokens_fn(part)
        added = (pt + joiner_tok) if buf else pt
        if buf and buf_tokens + added > max_tokens:
            ct = joiner.join(buf)
            spans.append(TextSpan(text=ct, start=pos, end=pos + len(ct)))
            pos += len(ct) + len(joiner)
            buf, buf_tokens = [], 0
            added = pt
        buf.append(part)
        buf_tokens += added

    if buf:
        ct = joiner.join(buf)
        spans.append(TextSpan(text=ct, start=pos, end=pos + len(ct)))

    return spans
