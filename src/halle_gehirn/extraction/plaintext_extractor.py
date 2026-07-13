"""Plaintext-Extractor fuer .md- und .txt-Dateien.

Liest Markdown- und reine Text-Dateien als ExtractedDoc.
.md-Dateien werden als-is als Markdown behandelt; .txt-Dateien
werden als einfache Absaetze in den body_md uebernommen.
Implementiert das Extractor-Protocol aus extraction/base.py.
"""
from __future__ import annotations

import re
from pathlib import Path

import structlog

from halle_gehirn.extraction.base import ExtractedDoc, ExtractionError

logger = structlog.get_logger(__name__)

_SUPPORTED: frozenset[str] = frozenset({".md", ".txt"})

_MD_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def _read_file(path: Path) -> str:
    """Liest eine Textdatei (UTF-8, Fallback latin-1).

    Args:
        path: Pfad zur Datei.

    Returns:
        Dateiinhalt als String.

    Raises:
        ExtractionError: Datei nicht gefunden oder nicht lesbar.
    """
    if not path.exists():
        raise ExtractionError(f"Datei nicht gefunden: {path}")
    if not path.is_file():
        raise ExtractionError(f"Kein regulaeres File: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def _extract_md_title(content: str, fallback: str) -> str:
    """Extrahiert den Titel aus dem ersten Markdown-Heading.

    Args:
        content: Markdown-Inhalt.
        fallback: Fallback-Titel (z.B. Dateiname).

    Returns:
        Extrahierter Titel oder Fallback.
    """
    match = _MD_TITLE_RE.search(content)
    return match.group(1).strip() if match else fallback


class PlaintextExtractor:
    """Extractor fuer .md- und .txt-Dateien.

    Implementiert das Extractor-Protocol aus extraction/base.py.
    """

    @property
    def supported_extensions(self) -> frozenset[str]:
        """Dateiendungen, die dieser Extractor verarbeitet."""
        return _SUPPORTED

    def extract(self, source: str | Path) -> ExtractedDoc:
        """Extrahiert Text aus einer .md- oder .txt-Datei.

        Args:
            source: Dateipfad.

        Returns:
            ExtractedDoc mit source_type="md" oder "txt".

        Raises:
            ExtractionError: Datei nicht lesbar oder unterstuetztes Format.
        """
        path = Path(source).resolve()
        suffix = path.suffix.lower()

        if suffix not in _SUPPORTED:
            raise ExtractionError(
                f"Nicht unterstuetztes Format: {suffix} "
                f"(erlaubt: {sorted(_SUPPORTED)})"
            )

        logger.info("plaintext_extraction_start", path=str(path), suffix=suffix)

        content = _read_file(path)
        source_type = suffix.lstrip(".")

        title = _extract_md_title(content, path.stem) if suffix == ".md" else path.stem

        doc = ExtractedDoc(
            source=str(path),
            source_type=source_type,
            title=title,
            body_md=content,
            tables=[],
            page_count=None,
            language="de",
            meta={
                "file_name": path.name,
                "file_size_bytes": str(path.stat().st_size),
            },
        )

        logger.info(
            "plaintext_extraction_done",
            path=str(path),
            title=title,
            chars=len(content),
        )
        return doc
