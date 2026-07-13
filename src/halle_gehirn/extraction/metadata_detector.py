"""Auto-Erkennung von Metadaten aus Dateiname und Dokumentinhalt.

Heuristiken fuer Titel, Jahr, Dokumenttyp, Grad, Bereich, Sorte
und Registry-Facetten (Thema, Anlage, Projekt, Ansprechperson).
Kein LLM, kein Netzwerkzugriff — rein regelbasiert.
"""
from __future__ import annotations

import io
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import structlog

from halle_gehirn.extraction.title_extractor import extract_title

logger = structlog.get_logger(__name__)

_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")

_PLAINTEXT_SUFFIXES: frozenset[str] = frozenset({".md", ".txt"})

_DOC_TYPE_KEYWORDS: list[tuple[str, str, str | None]] = [
    ("masterarbeit", "abschlussarbeit", "master"),
    ("master thesis", "abschlussarbeit", "master"),
    ("master's thesis", "abschlussarbeit", "master"),
    ("bachelorarbeit", "abschlussarbeit", "bachelor"),
    ("bachelor thesis", "abschlussarbeit", "bachelor"),
    ("projektbericht", "projektbericht", None),
    ("project report", "projektbericht", None),
    ("handbuch", "handbuch", None),
    ("betriebsanleitung", "handbuch", None),
    ("bedienungsanleitung", "handbuch", None),
    ("anlagendoku", "anlagendoku", None),
    ("flyer", "flyer", None),
    ("transkript", "experten_transkript", None),
    ("workshop", "workshop_slides", None),
    ("promotion", "promotion", None),
    ("dissertation", "promotion", None),
]

_SORTE_MAP: dict[str, str] = {
    "abschlussarbeit": "abschlussarbeiten",
    "promotion": "abschlussarbeiten",
    "projektbericht": "projektberichte",
    "handbuch": "anlagen",
    "anlagendoku": "anlagen",
    "flyer": "transfer",
    "workshop_slides": "transfer",
    "online_beitrag": "transfer",
    "experten_transkript": "transkripte",
    "video_transkript": "transkripte",
}

_BEREICH_MAP: dict[str, list[str]] = {
    "abschlussarbeit": ["lehre"],
    "promotion": ["forschung", "lehre"],
    "projektbericht": ["forschung"],
    "anlagendoku": ["infrastruktur"],
    "handbuch": ["infrastruktur"],
    "flyer": ["transfer"],
    "workshop_slides": ["transfer"],
    "online_beitrag": ["transfer"],
    "lehrbuch": ["lehre"],
}

_REGISTRY_FACETS: list[str] = ["thema", "anlage", "projekt", "ansprechperson"]


@dataclass
class MetadataSuggestion:
    """Auto-erkannte Metadaten-Vorschlaege fuer ein Dokument."""

    titel: str = ""
    doc_type: str | None = None
    grad: str | None = None
    bereich: list[str] = field(default_factory=list)
    herkunft: str = "lehrstuhl_at"
    quelltyp: str = "primaer"
    vertraulichkeit: str = "intern"
    status: str = "final"
    jahr: int | None = None
    sorte: str | None = None
    thema: list[str] = field(default_factory=list)
    anlage: list[str] = field(default_factory=list)
    projekt: list[str] = field(default_factory=list)
    ansprechperson: list[str] = field(default_factory=list)


def detect_metadata(
    filename: str,
    text: str,
    choices: dict[str, dict[str, str]],
) -> MetadataSuggestion:
    """Erkennt Metadaten aus Dateiname und extrahiertem Text.

    Args:
        filename: Originaler Dateiname des hochgeladenen Dokuments.
        text: Extrahierter Textinhalt (Markdown oder Plain).
        choices: Vokabular-Choices aus ``load_vokabular_choices()``.

    Returns:
        MetadataSuggestion mit best-effort vorausgefuellten Feldern.
    """
    titel = extract_title(text, filename)
    jahr = _detect_year(filename, text)
    doc_type, grad = _detect_doc_type_and_grad(filename, text)
    sorte = _SORTE_MAP.get(doc_type) if doc_type else None
    bereich = _BEREICH_MAP.get(doc_type, []) if doc_type else []
    facets = _detect_registry_facets(filename, text, choices)

    sug = MetadataSuggestion(
        titel=titel,
        doc_type=doc_type,
        grad=grad,
        bereich=bereich,
        jahr=jahr,
        sorte=sorte,
        thema=facets.get("thema", []),
        anlage=facets.get("anlage", []),
        projekt=facets.get("projekt", []),
        ansprechperson=facets.get("ansprechperson", []),
    )
    logger.info("metadata_detected", filename=filename, suggestion=sug)
    return sug


def extract_text_from_upload(file_data: bytes, filename: str) -> str:
    """Extrahiert Text aus hochgeladenen Datei-Bytes.

    Fuer .md/.txt: dekodiert Bytes direkt.
    Fuer PDF: pypdf (leichtgewichtig, erste 10 Seiten).
    Fuer DOCX/PPTX/XLSX: Temp-Datei + DoclingExtractor.
    Bei Fehler: leerer String (Erkennung nutzt dann Dateinamen).

    Args:
        file_data: Rohe Dateiinhalte.
        filename: Originaler Dateiname (bestimmt Format).

    Returns:
        Extrahierter Text (max. 10000 Zeichen). Leer bei Fehler.
    """
    suffix = Path(filename).suffix.lower()

    if suffix in _PLAINTEXT_SUFFIXES:
        return _decode_text(file_data)

    if suffix == ".pdf":
        return _extract_pdf_lightweight(file_data)

    return _extract_via_docling(file_data, suffix)


# ── Private Helfer ──────────────────────────────────────────────


def _decode_text(data: bytes) -> str:
    """Dekodiert Bytes als UTF-8, Fallback latin-1."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _extract_pdf_lightweight(file_data: bytes, max_pages: int = 10) -> str:
    """Extrahiert Text aus PDF via pypdf (erste N Seiten).

    Leichtgewichtig, kein Docling/OCR — vermeidet std::bad_alloc
    bei grossen PDFs. Fuer Metadaten-Erkennung voellig ausreichend.

    Args:
        file_data: Rohe PDF-Bytes.
        max_pages: Maximale Seitenzahl (Default: 10).

    Returns:
        Extrahierter Text (max. 10000 Zeichen). Leer bei Fehler.
    """
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(file_data))
        pages = reader.pages[:max_pages]
        parts: list[str] = []
        for page in pages:
            text = page.extract_text() or ""
            parts.append(text)
        return "\n\n".join(parts)[:10_000]
    except Exception:
        logger.warning("pypdf_extraction_failed", exc_info=True)
        return ""


def _extract_via_docling(file_data: bytes, suffix: str) -> str:
    """Extrahiert Text via DoclingExtractor ueber Temp-Datei."""
    try:
        from halle_gehirn.extraction.docling_extractor import DoclingExtractor

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_data)
            tmp_path = Path(tmp.name)
        try:
            doc = DoclingExtractor().extract(tmp_path)
            return doc.body_md[:10_000]
        finally:
            tmp_path.unlink(missing_ok=True)
    except Exception:
        logger.warning("docling_extraction_failed", suffix=suffix, exc_info=True)
        return ""


def _detect_year(filename: str, text: str) -> int | None:
    """Erkennt Jahreszahl aus Dateiname (Prioritaet), dann Text."""
    current_year = datetime.now().year
    # Dateiname zuerst
    for match in _YEAR_RE.finditer(filename):
        year = int(match.group(1))
        if 1990 <= year <= current_year + 1:
            return year
    # Dann Text (erste 2000 Zeichen)
    for match in _YEAR_RE.finditer(text[:2000]):
        year = int(match.group(1))
        if 1990 <= year <= current_year + 1:
            return year
    return None


def _detect_doc_type_and_grad(
    filename: str,
    text: str,
) -> tuple[str | None, str | None]:
    """Erkennt Dokumenttyp und Grad via Keyword-Matching."""
    search_text = (filename + " " + text[:3000]).lower()
    for keyword, doc_type, grad in _DOC_TYPE_KEYWORDS:
        if keyword in search_text:
            return doc_type, grad
    return None, None


def _detect_registry_facets(
    filename: str,
    text: str,
    choices: dict[str, dict[str, str]],
) -> dict[str, list[str]]:
    """Matched Vokabular-Labels case-insensitive gegen Text."""
    search_text = (filename + " " + text[:5000]).lower()
    result: dict[str, list[str]] = {}
    for facet in _REGISTRY_FACETS:
        slugs = choices.get(facet, {})
        matched: list[str] = []
        for slug, label in slugs.items():
            if label.lower() in search_text or slug in search_text:
                matched.append(slug)
        if matched:
            result[facet] = matched
    return result
