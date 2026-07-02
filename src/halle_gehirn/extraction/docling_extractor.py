"""Docling-basierter Extractor -- primaeres Extraction-Rueckgrat.

Konvertiert PDF, DOCX, PPTX, XLSX, HTML und Bilder via IBM Docling zu
strukturiertem Markdown mit Tabellen- und Seiten-Extraktion. OCR,
Table-Mode und Figure-Erkennung werden ueber config.py gesteuert.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    OcrAutoOptions,
    PdfPipelineOptions,
    TableFormerMode,
    TableStructureOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.extraction.base import (
    ExtractedDoc,
    ExtractionError,
    TableBlock,
)

logger = structlog.get_logger(__name__)

_SUPPORTED: frozenset[str] = frozenset({
    ".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp",
})


class DoclingExtractor:
    """Extractor-Implementierung auf Basis von IBM Docling.

    Unterstuetzt PDF, DOCX, PPTX, XLSX, HTML und gaengige Bildformate.
    Konfiguration (OCR, Tabellen-Modus, Abbildungen) wird aus den
    zentralen Settings gelesen.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._converter: DocumentConverter | None = None

    @property
    def supported_extensions(self) -> frozenset[str]:
        """Dateiendungen, die dieser Extractor verarbeitet."""
        return _SUPPORTED

    def extract(self, source: str | Path) -> ExtractedDoc:
        """Extrahiert ein Dokument zu einem ExtractedDoc.

        Args:
            source: Dateipfad zur Quelldatei.

        Returns:
            Strukturiertes ExtractedDoc mit Markdown, Tabellen, Meta.

        Raises:
            ExtractionError: Konvertierung fehlgeschlagen.
            FileNotFoundError: Datei existiert nicht.
        """
        path = Path(source).resolve()
        _validate_path(path)
        logger.info(
            "docling_extraction_start",
            path=str(path),
            suffix=path.suffix.lower(),
            size_bytes=path.stat().st_size,
        )
        docling_doc = self._convert(path)
        return self._build_result(docling_doc, path)

    def _convert(self, path: Path) -> Any:
        """Fuehrt die Docling-Konvertierung durch.

        Args:
            path: Aufgeloester Dateipfad.

        Returns:
            Docling-Dokument-Objekt.

        Raises:
            ExtractionError: Konvertierung fehlgeschlagen.
        """
        try:
            converter = self._get_converter()
            result = converter.convert(str(path))
            return result.document
        except ExtractionError:
            raise
        except Exception as exc:
            logger.error(
                "docling_conversion_failed", path=str(path), error=str(exc),
            )
            raise ExtractionError(
                f"Docling-Konvertierung fehlgeschlagen fuer {path.name}: {exc}"
            ) from exc

    def _build_result(self, docling_doc: Any, path: Path) -> ExtractedDoc:
        """Baut ein ExtractedDoc aus dem Docling-Ergebnis.

        Args:
            docling_doc: Konvertiertes Docling-Dokument.
            path: Original-Dateipfad.

        Returns:
            Fertiges ExtractedDoc.
        """
        body_md = docling_doc.export_to_markdown()
        tables = _extract_tables(docling_doc)
        page_count = _count_pages(docling_doc)
        title = _extract_title(docling_doc, fallback=path.stem)
        source_type = path.suffix.lstrip(".").lower()
        extracted = ExtractedDoc(
            source=str(path),
            source_type=source_type,
            title=title,
            body_md=body_md,
            tables=tables,
            page_count=page_count,
            language="de",
            meta=_build_meta(path),
        )
        logger.info(
            "docling_extraction_done",
            path=str(path),
            pages=page_count,
            tables=len(tables),
            md_chars=len(body_md),
        )
        return extracted

    def _get_converter(self) -> DocumentConverter:
        """Erstellt oder gibt den gecachten DocumentConverter zurueck."""
        if self._converter is None:
            self._converter = _build_converter(self._settings)
        return self._converter


# -- module-level helpers -------------------------------------------------


def _validate_path(path: Path) -> None:
    """Prueft Existenz und unterstuetztes Format.

    Args:
        path: Aufgeloester Dateipfad.

    Raises:
        FileNotFoundError: Datei nicht vorhanden.
        ExtractionError: Dateiendung nicht unterstuetzt.
    """
    if not path.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {path}")
    suffix = path.suffix.lower()
    if suffix not in _SUPPORTED:
        raise ExtractionError(
            f"Nicht unterstuetztes Format: {suffix} "
            f"(erlaubt: {sorted(_SUPPORTED)})"
        )


def _build_converter(settings: Settings) -> DocumentConverter:
    """Erstellt einen Docling DocumentConverter aus den Settings.

    Args:
        settings: Typisierte Laufzeit-Konfiguration.

    Returns:
        Konfigurierter DocumentConverter.
    """
    table_mode = (
        TableFormerMode.ACCURATE
        if settings.docling_table_mode == "accurate"
        else TableFormerMode.FAST
    )
    pipeline_options = PdfPipelineOptions(
        do_table_structure=True,
        table_structure_options=TableStructureOptions(mode=table_mode),
        do_ocr=settings.docling_ocr,
        ocr_options=OcrAutoOptions(lang=["de", "en"]),
        generate_picture_images=settings.docling_do_figures,
    )
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
            ),
        },
    )


def _extract_tables(docling_doc: Any) -> list[TableBlock]:
    """Extrahiert Tabellen als TableBlock-Liste.

    Args:
        docling_doc: Das konvertierte Docling-Dokument.

    Returns:
        Liste von TableBlock-Objekten.
    """
    tables: list[TableBlock] = []
    for table in getattr(docling_doc, "tables", []):
        md = _table_to_markdown(table, docling_doc)
        if not md:
            continue
        page_no = _get_page_number(table)
        caption = getattr(table, "caption", None)
        caption_str = str(caption).strip() if caption else None
        tables.append(
            TableBlock(markdown=md, page=page_no, caption=caption_str)
        )
    return tables


def _table_to_markdown(table: Any, docling_doc: Any) -> str:
    """Konvertiert eine Docling-Tabelle zu Markdown.

    Args:
        table: Docling-Tabellen-Objekt.
        docling_doc: Eltern-Dokument (fuer export_to_markdown API).

    Returns:
        Markdown-String der Tabelle (leer bei Fehler).
    """
    export_fn = getattr(table, "export_to_markdown", None)
    if callable(export_fn):
        try:
            result: str = export_fn(doc=docling_doc)
            return result
        except TypeError:
            # Fallback fuer aeltere Docling-Versionen ohne doc-Parameter
            try:
                result = export_fn()
                return result
            except Exception:
                pass
        except Exception:
            pass
    data = getattr(table, "data", None)
    if data and hasattr(data, "grid"):
        return _grid_to_markdown(data.grid)
    return ""


def _grid_to_markdown(grid: list[list[Any]]) -> str:
    """Konvertiert ein Docling-Tabellen-Grid zu Markdown-Tabelle."""
    if not grid:
        return ""
    lines: list[str] = []
    header = [str(c) for c in grid[0]]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in grid[1:]:
        cells = [str(c) for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    return chr(10).join(lines)


def _get_page_number(element: Any) -> int | None:
    """Liest die Seitennummer aus einem Docling-Element."""
    prov = getattr(element, "prov", None)
    if prov and len(prov) > 0:
        return getattr(prov[0], "page_no", None)
    return None


def _count_pages(docling_doc: Any) -> int | None:
    """Zaehlt die Seiten im Docling-Dokument."""
    pages = getattr(docling_doc, "pages", None)
    if pages:
        return len(pages)
    return None


def _extract_title(docling_doc: Any, fallback: str) -> str:
    """Holt den Titel aus Docling-Metadaten oder Dateiname."""
    name = getattr(docling_doc, "name", None)
    if name and str(name).strip():
        return str(name).strip()
    return fallback


def _build_meta(path: Path) -> dict[str, str]:
    """Erzeugt Metadaten-Dict aus Dateieigenschaften."""
    stat = path.stat()
    return {
        "file_name": path.name,
        "file_size_bytes": str(stat.st_size),
    }

