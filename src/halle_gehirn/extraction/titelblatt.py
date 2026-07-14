"""BTU-Titelblatt-Parser: Autor, Betreuer, Studiengang, Datum.

Regelbasierter Parser fuer die ersten Seiten deutscher Abschlussarbeiten
im BTU-Format. Liefert Vorschlaege fuer die Manifest-Kuration
(Human-in-the-Loop — KEIN Auto-Write ins Manifest).

DSGVO: Matrikelnummern werden bewusst NICHT extrahiert.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)

# Wie viele Zeichen vom Dokumentanfang als Titelblatt gelten
_TITELBLATT_CHARS = 4000

# Namens-Kern: 2-4 kapitalisierte Woerter auf EINER Zeile
# ([ \t] statt \s — sonst frisst der Match die Folgezeile mit)
_NAME = r"([A-ZÄÖÜ][a-zäöüß\-]+(?:[ \t]+[A-ZÄÖÜ][a-zäöüß\-]+){1,3})"

# "vorgelegt von: Max Mustermann" / "eingereicht von Frau Erika Musterfrau"
_AUTOR_RE = re.compile(
    r"(?:vorgelegt|eingereicht|verfasst|erstellt|angefertigt)\s+von\s*:?\s*"
    r"(?:Herrn[ \t]+|Frau[ \t]+)?" + _NAME,
)

# "Autor: Max Mustermann" / "Autorin:"
_AUTOR_LABEL_RE = re.compile(r"Autor(?:in)?\s*:[ \t]*" + _NAME)

# "Betreuer:", "1. Gutachter:", "2. Prüferin:", "Erstgutachter:",
# "Zweitgutachterin:" — Komposita schreiben den Rollennamen klein
_BETREUER_RE = re.compile(
    r"(?:(?:[12]\.|Erst|Zweit)[ \t]*-?[ \t]*)?"
    r"(?:[Bb]etreuer(?:in)?|[Gg]utachter(?:in)?|[Pp]r(?:ue|ü)fer(?:in)?)"
    r"\s*:\s*([^\n]{3,80})",
)

# "Studiengang: Elektrotechnik" / "im Masterstudiengang Maschinenbau"
_STUDIENGANG_RE = re.compile(
    r"(?:Master-?|Bachelor-?)?[Ss]tudiengang\s*:?\s*"
    r"[„\"]?([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\- ]{3,60})",
)

# "Cottbus, den 15.03.2025" bzw. beliebiges deutsches Datum
_DATUM_RE = re.compile(
    r"\b\d{1,2}\.\s?\d{1,2}\.\s?((?:19|20)\d{2})\b",
)

# Akademische Titel-Tokens (werden aus Namen entfernt)
_TITLE_TOKEN_RE = re.compile(
    r"^(?:prof|dr|ing|dipl|habil|med|rer|nat|pol|univ|"
    r"m|b|sc|eng|a|mag|phil|h|c)[.\-]*$",
    re.IGNORECASE,
)

_UMLAUT_MAP = str.maketrans({
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "ae", "Ö": "oe", "Ü": "ue",
})


@dataclass(frozen=True)
class TitelblattInfo:
    """Vom Titelblatt extrahierte Vorschlaege (best effort)."""

    autor: str | None = None
    betreuer: list[str] = field(default_factory=list)
    studiengang: str | None = None
    jahr: int | None = None


def parse_titelblatt(text: str) -> TitelblattInfo:
    """Parst die Titelblatt-Angaben aus dem Dokumentanfang.

    Args:
        text: Extrahierter Dokumenttext (nur der Anfang wird gelesen).

    Returns:
        TitelblattInfo mit erkannten Feldern (None/leer = nicht gefunden).
    """
    head = text[:_TITELBLATT_CHARS]

    autor = _find_autor(head)
    betreuer = _find_betreuer(head)
    studiengang = _find_studiengang(head)
    jahr = _find_jahr(head)

    info = TitelblattInfo(
        autor=autor,
        betreuer=betreuer,
        studiengang=studiengang,
        jahr=jahr,
    )
    logger.debug(
        "titelblatt_parsed",
        autor=autor,
        betreuer=betreuer,
        studiengang=studiengang,
        jahr=jahr,
    )
    return info


def nachname_slug(name: str) -> str:
    """Leitet den Registry-Slug (Nachname, lowercase, ae/oe/ue) ab.

    Args:
        name: Voller Name (z.B. "Prof. Dr. Kim Berger").

    Returns:
        Slug wie "berger" — passend zu data/vokabular.yaml.
    """
    cleaned = _clean_name(name)
    if not cleaned:
        return ""
    nachname = cleaned.split()[-1]
    return nachname.lower().translate(_UMLAUT_MAP)


# ── Private Helfer ──────────────────────────────────────────────


def _clean_name(raw: str) -> str:
    """Entfernt akademische Titel und Nicht-Namens-Tokens."""
    tokens: list[str] = []
    for token in raw.replace(",", " ").split():
        bare = token.strip(".-")
        if not bare or _TITLE_TOKEN_RE.match(bare):
            continue
        if "." in token:  # Initialen wie "K." oder Reste wie "M.Eng."
            continue
        if not bare[0].isupper():
            continue
        tokens.append(bare)
    return " ".join(tokens)


def _find_autor(head: str) -> str | None:
    """Sucht den Verfasser (vorgelegt von … / Autor: …)."""
    for pattern in (_AUTOR_RE, _AUTOR_LABEL_RE):
        match = pattern.search(head)
        if match:
            name = _clean_name(match.group(1))
            if name:
                return name
    return None


def _find_betreuer(head: str) -> list[str]:
    """Sammelt Betreuer/Gutachter/Pruefer (dedupliziert, in Reihenfolge)."""
    seen: set[str] = set()
    result: list[str] = []
    for match in _BETREUER_RE.finditer(head):
        name = _clean_name(match.group(1))
        if name and name.lower() not in seen:
            seen.add(name.lower())
            result.append(name)
    return result


def _find_studiengang(head: str) -> str | None:
    """Sucht den Studiengang."""
    match = _STUDIENGANG_RE.search(head)
    if not match:
        return None
    return " ".join(match.group(1).split()).strip(" -")


def _find_jahr(head: str) -> int | None:
    """Sucht ein deutsches Datum (TT.MM.JJJJ) und liefert das Jahr.

    Praeziser als die Erste-Jahreszahl-Heuristik, die auf dem
    Titelblatt auch Norm- oder Versionsnummern treffen kann.
    """
    match = _DATUM_RE.search(head)
    if match:
        return int(match.group(1))
    return None
