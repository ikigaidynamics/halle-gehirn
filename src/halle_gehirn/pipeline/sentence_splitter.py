"""Deutscher Satz-Splitter mit Abkuerzungs-Schutz.

Zerlegt deutschen Fliesstext in Saetze unter Beruecksichtigung gaengiger
deutscher Abkuerzungen (z.B., d.h., Prof., Dr.) und akademischer Titel,
damit diese nicht faelschlich als Satzenden erkannt werden.
"""
from __future__ import annotations

import re
from typing import NamedTuple

# ── Deutsche Abkuerzungen (lowercase, OHNE abschliessenden Punkt) ──
_ABBREV: frozenset[str] = frozenset({
    # Alltags-Abkuerzungen
    "z", "b", "d", "h", "u", "a", "s", "o",
    "bspw", "bzgl", "bzw", "ca", "etc", "evtl", "ggf", "inkl", "insb",
    "max", "min", "nr", "vgl", "vs", "usw", "sog", "rd",
    # Mehrteilige (z.B., d.h., u.a., i.d.R., o.ä.)
    "z.b", "d.h", "u.a", "s.o", "s.u", "o.g", "u.g", "i.d.r",
    "i.a", "z.t", "o.ä", "u.ä", "u.u", "z.zt",
    # Akademische Titel
    "prof", "dr", "ing", "dipl", "habil", "mag", "doz",
    # Publikations-Kuerzel
    "abs", "abb", "anm", "aufl", "bd", "bes", "dgl", "ebd",
    "gem", "hrsg", "jg", "kap", "mio", "mrd", "tab", "tel", "tsd",
    # Technische Kuerzel (Maschinenbereich)
    "gl", "abschn", "anh",
})

# Numerische Muster: "1.", "2.", "3.1." usw. — keine Satzgrenze
_NUMERIC_ENUM = re.compile(r"^\d+(\.\d+)*$")

# Placeholder fuer geschuetzte Punkte
_DOT_PLACEHOLDER = "\x00"


class Sentence(NamedTuple):
    """Ein Satz mit Zeichenoffsets im Quelltext."""

    text: str
    start: int
    end: int


def split_sentences(text: str) -> list[Sentence]:
    """Zerlegt *text* in Saetze mit Zeichen-Offsets.

    Args:
        text: Deutscher Fliesstext (Markdown OK, Tabellen vorher abtrennen).

    Returns:
        Liste von ``Sentence``-Tupeln (text, start, end).
    """
    if not text or not text.strip():
        return []
    protected, _map = _protect(text)
    raw_spans = _split_raw(protected)
    return _to_sentences(raw_spans, text)


def _protect(text: str) -> tuple[str, None]:
    """Ersetzt Punkte in Abkuerzungen durch Placeholder."""
    result = list(text)
    i = 0
    while i < len(result):
        if result[i] == ".":
            word = _word_before(result, i)
            if word and _is_abbreviation(word):
                result[i] = _DOT_PLACEHOLDER
        i += 1
    return "".join(result), None


def _word_before(chars: list[str], pos: int) -> str:
    """Extrahiert das Wort direkt vor Position *pos*."""
    end = pos
    start = pos - 1
    while start >= 0 and (chars[start].isalnum() or chars[start] in ".-"):
        start -= 1
    return "".join(chars[start + 1 : end])


def _is_abbreviation(word: str) -> bool:
    """Prueft ob *word* eine bekannte Abkuerzung ist."""
    clean = word.lower().rstrip(".")
    if clean in _ABBREV:
        return True
    # Mehrteilige: z.B → z.b
    if _DOT_PLACEHOLDER in clean:
        clean = clean.replace(_DOT_PLACEHOLDER, ".")
    if clean in _ABBREV:
        return True
    # Numerische Aufzaehlung: 1, 2, 3.1
    return bool(_NUMERIC_ENUM.match(clean))


_BOUNDARY = re.compile(
    r"(?<=[.!?])"   # nach Satzzeichen
    r"[\s]+"         # Whitespace
    r"(?=[A-ZÄÖÜ])"  # naechster Satz beginnt mit Grossbuchstabe
)


def _split_raw(text: str) -> list[tuple[int, int]]:
    """Findet Satzgrenzen und gibt (start, end)-Spannen zurueck."""
    spans: list[tuple[int, int]] = []
    prev = 0
    for m in _BOUNDARY.finditer(text):
        split_pos = m.start()
        spans.append((prev, split_pos))
        prev = m.end()
    if prev < len(text):
        spans.append((prev, len(text)))
    return spans


def _to_sentences(
    spans: list[tuple[int, int]], original: str,
) -> list[Sentence]:
    """Wandelt Roh-Spannen in Sentence-Objekte um."""
    sentences: list[Sentence] = []
    for start, end in spans:
        raw = original[start:end].strip()
        if not raw:
            continue
        # Finde tatsaechlichen Start/Ende im Original (ohne fuehrendes WS)
        actual_start = start
        while actual_start < end and original[actual_start] in " \t\n\r":
            actual_start += 1
        actual_end = end
        while actual_end > actual_start and original[actual_end - 1] in " \t\n\r":
            actual_end -= 1
        if actual_start < actual_end:
            sentences.append(Sentence(
                text=original[actual_start:actual_end],
                start=actual_start,
                end=actual_end,
            ))
    return sentences
