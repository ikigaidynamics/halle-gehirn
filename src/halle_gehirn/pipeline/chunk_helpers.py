"""Hilfstypen und -funktionen fuer den Chunker.

Enthaelt Section-Splitting (Markdown an Headings zerlegen) und
Tabellen-Splitting (uebergrosse Markdown-Tabellen an Zeilengrenzen
teilen, Header wird in jedem Teil wiederholt).
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

    Args:
        body: Markdown-Text.

    Returns:
        Liste von Sections mit Text-Offsets.
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

    for i, match in enumerate(heading_matches):
        heading_text = normalize_heading(match.group(2))
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
            headings=[heading_text],
        ))
    return sections


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
