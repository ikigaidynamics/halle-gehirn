"""Deterministische Reparatur von Extraktions-Artefakten.

Bereinigt typische Fehler aus der PDF-Extraktion (OCR oder defekte
Textebene): fehlgeleitete Kodierungen, aufgeloeste Ligaturen,
getrennte LaTeX-Diakritika, Silbentrennungen und HTML-Reste in
Tabellenzellen.

Wird NACH der Extraktion und VOR dem Chunking ausgefuehrt, damit
Embeddings und Sparse-Index sauberen Text sehen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Statistik-Container
# ---------------------------------------------------------------------------


@dataclass
class SanitizerStats:
    """Zaehlt Ersetzungen pro Regel fuer ein Dokument."""

    ypsilon_to_eszett: int = 0
    ligature_restored: int = 0
    diacritic_combined: int = 0
    hyphenation_joined: int = 0
    br_tags_removed: int = 0
    table_syllable_joined: int = 0
    table_syllable_uncertain: int = 0
    ligature_details: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return (
            self.ypsilon_to_eszett
            + self.ligature_restored
            + self.diacritic_combined
            + self.hyphenation_joined
            + self.br_tags_removed
            + self.table_syllable_joined
        )

    def as_dict(self) -> dict[str, int]:
        d: dict[str, int] = {
            "ypsilon_to_eszett": self.ypsilon_to_eszett,
            "ligature_restored": self.ligature_restored,
            "diacritic_combined": self.diacritic_combined,
            "hyphenation_joined": self.hyphenation_joined,
            "br_tags_removed": self.br_tags_removed,
            "table_syllable_joined": self.table_syllable_joined,
            "table_syllable_uncertain": self.table_syllable_uncertain,
            "total": self.total,
        }
        if self.ligature_details:
            d["ligature_details"] = self.ligature_details  # type: ignore[assignment]
        return d


# ---------------------------------------------------------------------------
# 1) ÿ → ß  (nur im Kleinbuchstaben-Kontext)
# ---------------------------------------------------------------------------

# ÿ nur ersetzen wenn es INNERHALB eines kleingeschriebenen Wortes steht.
# Negativbeispiel: Name "Ÿves" oder alleinstehend.
_YPSILON_RE = re.compile(r"(?<=[a-zäöüé])ÿ(?=[a-zäöüé])")


def _fix_eszett(text: str, stats: SanitizerStats) -> str:
    count = len(_YPSILON_RE.findall(text))
    if count:
        text = _YPSILON_RE.sub("ß", text)
        stats.ypsilon_to_eszett = count
    return text


# ---------------------------------------------------------------------------
# 2) Steuerzeichen / Replacement-Chars → Ligaturen
# ---------------------------------------------------------------------------

# Bekannte Steuerzeichen-Mappings aus Docling-Extraktion.
# U+001B (ESC) tritt als haeufigster Ligatur-Ersatz auf (ff).
# U+FFFD (REPLACEMENT CHARACTER) ebenfalls moeglich.
# Unicode-Ligatur-Codepoints die manche Extraktoren ausgeben:
_LIGATURE_MAP: dict[str, str] = {
    "\u001b": "ff",     # ESC → ff  (häufigster Fall)
    "\ufb00": "ff",     # ﬀ  (Unicode-Ligatur ff)
    "\ufb01": "fi",     # ﬁ  (Unicode-Ligatur fi)
    "\ufb02": "fl",     # ﬂ  (Unicode-Ligatur fl)
    "\ufb03": "ffi",    # ﬃ  (Unicode-Ligatur ffi)
    "\ufb04": "ffl",    # ﬄ  (Unicode-Ligatur ffl)
}

# Pattern: jedes der Zeichen innerhalb von Wort-Kontext
_LIGATURE_CHARS = "".join(re.escape(c) for c in _LIGATURE_MAP)
_LIGATURE_RE = re.compile(f"[{_LIGATURE_CHARS}]")


def _fix_ligatures(text: str, stats: SanitizerStats) -> str:
    def _replace(m: re.Match[str]) -> str:
        ch = m.group()
        replacement = _LIGATURE_MAP[ch]
        stats.ligature_details[replacement] = (
            stats.ligature_details.get(replacement, 0) + 1
        )
        return replacement

    new_text = _LIGATURE_RE.sub(_replace, text)
    stats.ligature_restored = sum(stats.ligature_details.values())
    return new_text


# ---------------------------------------------------------------------------
# 3) LaTeX-Diakritika rekombinieren: ¨ + Vokal → Umlaut
# ---------------------------------------------------------------------------

# Sowohl U+00A8 (DIAERESIS) als auch das Muster \" + Vokal (aus manchen
# Extraktoren) abfangen.  Auch Grossbuchstaben.
_DIACRITIC_MAP: dict[str, str] = {
    "a": "ä", "o": "ö", "u": "ü",
    "A": "Ä", "O": "Ö", "U": "Ü",
}

# ¨ (U+00A8) direkt vor Vokal — ggf. mit einem optionalen Leerzeichen
_DIAERESIS_RE = re.compile(
    r"\u00a8\s?([aouAOU])"
)

# Alternatives Pattern: Backslash-Quote \" gefolgt von Vokal
# (LaTeX-Rohsyntax die manchmal durchkommt)
_LATEX_UMLAUT_RE = re.compile(
    r'\\"\s?([aouAOU])'
)


def _fix_diacritics(text: str, stats: SanitizerStats) -> str:
    count = 0

    def _combine(m: re.Match[str]) -> str:
        nonlocal count
        vowel = m.group(1)
        replacement = _DIACRITIC_MAP.get(vowel)
        if replacement:
            count += 1
            return replacement
        return m.group()  # Sollte nicht vorkommen, aber sicher ist sicher

    text = _DIAERESIS_RE.sub(_combine, text)
    text = _LATEX_UMLAUT_RE.sub(_combine, text)
    stats.diacritic_combined = count
    return text


# ---------------------------------------------------------------------------
# 4) Silbentrennung zusammenfuehren
# ---------------------------------------------------------------------------

# Wort-Fragment + Bindestrich + Newline(s) + Kleinbuchstabe → zusammenziehen.
# NUR wenn nach dem Umbruch KLEIN weitergeht (sonst echtes Kompositum).
# Auch Tabulator / Leerzeichen nach Newline erlaubt.
_HYPHEN_RE = re.compile(
    r"(\w)[-\u00AD]\s*\n[ \t]*([a-zäöüß])"
)


def _fix_hyphenation(text: str, stats: SanitizerStats) -> str:
    count = len(_HYPHEN_RE.findall(text))
    if count:
        text = _HYPHEN_RE.sub(r"\1\2", text)
        stats.hyphenation_joined = count
    return text


# ---------------------------------------------------------------------------
# 5) <br>-Tags in Tabellenzellen → Leerzeichen
# ---------------------------------------------------------------------------

_BR_TAG_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def _fix_br_tags(text: str, stats: SanitizerStats) -> str:
    count = len(_BR_TAG_RE.findall(text))
    if count:
        text = _BR_TAG_RE.sub(" ", text)
        stats.br_tags_removed = count
    return text


# ---------------------------------------------------------------------------
# 6) Silbenumbrueche OHNE Trennstrich in Tabellenzellen
# ---------------------------------------------------------------------------

# Gaengige deutsche Kurzwoerter (2-3 Buchstaben) die NICHT an ein vorangehendes
# Wort geklebt werden duerfen.  1-Buchstaben-Fragmente sind immer sicher
# (kein deutsches Wort ist ein einzelner Kleinbuchstabe).
_SAFE_SHORT_WORDS: frozenset[str] = frozenset({
    # 2 Buchstaben
    "ab", "am", "an", "da", "du", "er", "es", "im", "in",
    "ja", "je", "ob", "so", "um", "zu",
    # 3 Buchstaben
    "als", "auf", "aus", "bei", "bin", "bis", "das", "dem", "den",
    "der", "des", "die", "dir", "ein", "hat", "ich", "ihm", "ihn",
    "ihr", "ist", "mal", "man", "mir", "mit", "nie", "nun", "nur",
    "per", "pro", "sei", "sie", "tun", "und", "uns", "via", "vom",
    "von", "vor", "war", "was", "wem", "wen", "wer", "wie", "wir",
    "zog", "zum", "zur",
})

# Regel 6a: Langer Wortteil + 1 Leerzeichen + kurzes Fragment (1-3 Kleinbuchstaben)
_TABLE_SHORT_FRAG_RE = re.compile(
    r"([a-zäöüß]{3,})\s([a-zäöüß]{1,3})(?=\s|[|,;.)\]]|$)"
)

# Regel 6b: Langer Wortteil + 1 Leerzeichen + laengeres Fragment (≥4 Buchstaben)
_TABLE_LONG_FRAG_RE = re.compile(
    r"([a-zäöüß]{3,})\s([a-zäöüß]{4,})(?=\s|[|,;.)\]]|$)"
)


def _fix_table_syllables(
    text: str, stats: SanitizerStats, *, corpus: str = "",
) -> str:
    """Repariert Silbenumbrueche ohne Trennstrich in Tabellenzellen.

    Nur Zeilen die ``|`` enthalten werden bearbeitet (Markdown-Tabellen).
    Zwei Teil-Regeln:
      6a) Kurze Fragmente (1-3 Buchstaben): via Blockliste geschuetzt.
      6b) Lange Fragmente (≥4 Buchstaben): nur wenn das zusammengesetzte
          Wort im *corpus* vorkommt (Kreuzreferenz).

    Args:
        text: Markdown-Text (kann Tabellen- und Fliesstext-Zeilen enthalten).
        stats: Statistik-Container (wird in-place aktualisiert).
        corpus: Referenz-Text fuer Corpus-Lookup (z.B. ``doc.body_md``).
    """
    corpus_lower = corpus.lower() if corpus else ""
    lines = text.split("\n")
    changed = False

    for i, line in enumerate(lines):
        if "|" not in line:
            continue

        # ── Regel 6a: kurze Fragmente ──
        def _replace_short(m: re.Match[str]) -> str:
            nonlocal changed
            left, frag = m.group(1), m.group(2)
            if frag in _SAFE_SHORT_WORDS:
                stats.table_syllable_uncertain += 1
                logger.debug(
                    "sanitizer_uncertain",
                    rule="6a_short_blocklist",
                    left=left,
                    fragment=frag,
                )
                return m.group()
            changed = True
            stats.table_syllable_joined += 1
            return left + frag

        line = _TABLE_SHORT_FRAG_RE.sub(_replace_short, line)

        # ── Regel 6b: lange Fragmente (Corpus-Lookup) ──
        if corpus_lower:
            def _replace_long(m: re.Match[str]) -> str:
                nonlocal changed
                left, frag = m.group(1), m.group(2)
                combined = left + frag
                if combined.lower() in corpus_lower:
                    changed = True
                    stats.table_syllable_joined += 1
                    return combined
                stats.table_syllable_uncertain += 1
                logger.debug(
                    "sanitizer_uncertain",
                    rule="6b_corpus_miss",
                    left=left,
                    fragment=frag,
                    combined=combined,
                )
                return m.group()

            line = _TABLE_LONG_FRAG_RE.sub(_replace_long, line)

        lines[i] = line

    return "\n".join(lines) if changed else text


# ---------------------------------------------------------------------------
# Oeffentliche API
# ---------------------------------------------------------------------------


def sanitize(
    text: str, *, source: str = "", corpus: str = "",
) -> tuple[str, SanitizerStats]:
    """Bereinigt Extraktions-Artefakte deterministisch.

    Args:
        text: Roh-Markdown aus der Extraktion.
        source: Optionaler Dateiname fuer Logging.
        corpus: Referenz-Text fuer Corpus-basierte Regeln (z.B.
            ``doc.body_md`` als Kreuzreferenz fuer Tabellen-Silben).

    Returns:
        Tuple aus (bereinigter Text, Statistik).
    """
    if not text:
        return text, SanitizerStats()

    stats = SanitizerStats()

    text = _fix_eszett(text, stats)
    text = _fix_ligatures(text, stats)
    text = _fix_diacritics(text, stats)
    text = _fix_hyphenation(text, stats)
    text = _fix_br_tags(text, stats)
    text = _fix_table_syllables(text, stats, corpus=corpus)

    if stats.total > 0:
        logger.info(
            "sanitizer_stats",
            source=source,
            **stats.as_dict(),
        )

    return text, stats
