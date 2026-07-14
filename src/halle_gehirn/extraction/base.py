"""Basistypen und Extractor-Protocol fuer die Extraction-Schicht.

Definiert ExtractedDoc (Ergebnis jeder Extraktion) und das Extractor-Protocol,
das jeder konkrete Extractor implementiert (Docling, HTML, manual_loader).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class TableBlock:
    """Eine aus dem Dokument extrahierte Tabelle."""

    markdown: str
    page: int | None = None
    caption: str | None = None


@dataclass
class FigureBlock:
    """Eine aus dem Dokument extrahierte Abbildung."""

    image_path: str  # Relativer Pfad ab figures_dir ({hash}/{filename})
    page: int | None = None
    caption: str | None = None
    fig_index: int = 0


@dataclass
class ExtractedDoc:
    """Strukturiertes Ergebnis einer Dokument-Extraktion.

    Enthaelt den Volltext als Markdown, optional extrahierte Tabellen,
    Seitenzahlen und Metadaten. Pipeline-Stufen (Chunker, Enricher)
    arbeiten auf dieser Struktur weiter.
    """

    source: str
    source_type: str  # pdf|docx|pptx|xlsx|html|manual|transcript
    title: str
    body_md: str
    tables: list[TableBlock] = field(default_factory=list)
    figures: list[FigureBlock] = field(default_factory=list)
    page_count: int | None = None
    language: str = "de"
    meta: dict[str, str] = field(default_factory=dict)
    # Seiten-Provenienz: (char_offset, page_no) aufsteigend — der Chunker
    # ordnet darueber jedem Body-Chunk seine Seite zu (leer = unbekannt)
    page_map: list[tuple[int, int]] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """Body + Tabellen-Markdown (fuer Chunker)."""
        parts = [self.body_md]
        for tbl in self.tables:
            parts.append(tbl.markdown)
        return "\n\n".join(parts)


@runtime_checkable
class Extractor(Protocol):
    """Protocol fuer alle Extractoren (Docling, HTML, manual_loader)."""

    def extract(self, source: str | Path) -> ExtractedDoc:
        """Extrahiert eine Quelle zu einem ExtractedDoc.

        Args:
            source: Dateipfad oder URL.

        Returns:
            Strukturiertes Dokument.

        Raises:
            ExtractionError: Bei nicht lesbarem/unterstuetztem Format.
        """
        ...

    @property
    def supported_extensions(self) -> frozenset[str]:
        """Dateiendungen, die dieser Extractor verarbeitet."""
        ...


class ExtractionError(Exception):
    """Fehler bei der Dokument-Extraktion."""


class PartialExtractionError(ExtractionError):
    """Extraktion lieferte nur einen Teil der Seiten (stille Datenverluste).

    Wird ausgeloest, wenn die primaere Pipeline (Docling) zu viele Seiten
    verliert und ein Fallback-Backend einspringen muss.
    """

    def __init__(
        self,
        message: str,
        *,
        failed_pages: int,
        total_pages: int,
    ) -> None:
        super().__init__(message)
        self.failed_pages = failed_pages
        self.total_pages = total_pages
