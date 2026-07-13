"""Docling-basierter Extractor -- primaeres Extraction-Rueckgrat.

Konvertiert PDF, DOCX, PPTX, XLSX, HTML und Bilder via IBM Docling zu
strukturiertem Markdown mit Tabellen- und Seiten-Extraktion. OCR,
Table-Mode und Figure-Erkennung werden ueber config.py gesteuert.

**Integritaetssicherung (fail-closed):**
Nach jeder Konvertierung wird ``result.status`` / ``result.errors``
geprueft. Wenn mehr als ``_MAX_PAGE_LOSS_RATIO`` der Seiten fehlschlagen,
springt ein pymupdf4llm-Fallback ein. Schlaegt auch dieser fehl,
wird ``ExtractionError`` geworfen -- stille Teilverluste sind
ausgeschlossen.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from docling.datamodel.base_models import ConversionStatus, InputFormat
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
    FigureBlock,
    PartialExtractionError,
    TableBlock,
)

logger = structlog.get_logger(__name__)

_SUPPORTED: frozenset[str] = frozenset({
    ".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp",
})

# Maximal tolerierter Anteil fehlgeschlagener Seiten (20 %).
# Ueberschritten -> Fallback.
_MAX_PAGE_LOSS_RATIO: float = 0.2


class DoclingExtractor:
    """Extractor-Implementierung auf Basis von IBM Docling.

    Unterstuetzt PDF, DOCX, PPTX, XLSX, HTML und gaengige Bildformate.
    Konfiguration (OCR, Tabellen-Modus, Abbildungen) wird aus den
    zentralen Settings gelesen.

    Bei PDFs wird nach der Konvertierung geprueft, ob signifikante
    Seitenverluste vorliegen. Falls ja, wird pymupdf4llm als
    Fallback verwendet.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._converter: DocumentConverter | None = None

    @property
    def supported_extensions(self) -> frozenset[str]:
        """Dateiendungen, die dieser Extractor verarbeitet."""
        return _SUPPORTED

    def extract(
        self,
        source: str | Path,
        *,
        do_ocr: bool | None = None,
    ) -> ExtractedDoc:
        """Extrahiert ein Dokument zu einem ExtractedDoc.

        Args:
            source: Dateipfad zur Quelldatei.
            do_ocr: OCR-Override (None = globale Einstellung aus Config).

        Returns:
            Strukturiertes ExtractedDoc mit Markdown, Tabellen, Meta.

        Raises:
            ExtractionError: Konvertierung fehlgeschlagen (auch Fallback).
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

        try:
            docling_doc = self._convert(path, do_ocr=do_ocr)
            return self._build_result(docling_doc, path)
        except PartialExtractionError as exc:
            if path.suffix.lower() != ".pdf":
                raise ExtractionError(str(exc)) from exc
            logger.warning(
                "docling_fallback_triggered",
                path=str(path),
                failed_pages=exc.failed_pages,
                total_pages=exc.total_pages,
            )
            return self._pymupdf_fallback(path)
        except ExtractionError:
            # Docling komplett gescheitert -- Fallback versuchen
            if path.suffix.lower() == ".pdf":
                logger.warning(
                    "docling_crash_fallback", path=str(path),
                )
                return self._pymupdf_fallback(path)
            raise

    def _convert(
        self,
        path: Path,
        *,
        do_ocr: bool | None = None,
    ) -> Any:
        """Fuehrt die Docling-Konvertierung durch und prueft Integritaet.

        Args:
            path: Aufgeloester Dateipfad.
            do_ocr: OCR-Override (None = Config-Default).

        Returns:
            Docling-Dokument-Objekt.

        Raises:
            PartialExtractionError: Zu viele Seiten fehlgeschlagen.
            ExtractionError: Konvertierung komplett fehlgeschlagen.
        """
        try:
            converter = self._get_converter(do_ocr=do_ocr)
            result = converter.convert(str(path))
        except ExtractionError:
            raise
        except Exception as exc:
            logger.error(
                "docling_conversion_failed",
                path=str(path),
                error=str(exc),
            )
            raise ExtractionError(
                f"Docling-Konvertierung fehlgeschlagen fuer {path.name}: {exc}"
            ) from exc

        # -- Integritaetspruefung (fail-closed) --
        _check_conversion_integrity(result, path)

        return result.document

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
        source_hash = _compute_path_hash(path)
        figures = _extract_figures(
            docling_doc, source_hash, self._settings,
        )
        page_count = _count_pages(docling_doc)
        title = _extract_title(docling_doc, fallback=path.stem)
        source_type = path.suffix.lstrip(".").lower()
        extracted = ExtractedDoc(
            source=str(path),
            source_type=source_type,
            title=title,
            body_md=body_md,
            tables=tables,
            figures=figures,
            page_count=page_count,
            language="de",
            meta=_build_meta(path),
        )
        logger.info(
            "docling_extraction_done",
            path=str(path),
            pages=page_count,
            tables=len(tables),
            figures=len(figures),
            md_chars=len(body_md),
        )
        return extracted

    def _pymupdf_fallback(self, path: Path) -> ExtractedDoc:
        """Fallback-Extraktion via pymupdf4llm fuer PDFs.

        Args:
            path: Aufgeloester Pfad zur PDF-Datei.

        Returns:
            ExtractedDoc aus pymupdf4llm-Markdown.

        Raises:
            ExtractionError: Auch der Fallback ist fehlgeschlagen.
        """
        try:
            import pymupdf
            import pymupdf4llm
        except ImportError as exc:
            raise ExtractionError(
                f"pymupdf4llm nicht installiert -- Fallback fuer "
                f"{path.name} nicht moeglich"
            ) from exc

        logger.info("pymupdf4llm_fallback_start", path=str(path))

        try:
            body_md: str = pymupdf4llm.to_markdown(
                str(path), show_progress=False,
            )
            doc = pymupdf.open(str(path))
            page_count = len(doc)
            doc.close()
        except Exception as exc:
            logger.error(
                "pymupdf4llm_fallback_failed",
                path=str(path),
                error=str(exc),
            )
            raise ExtractionError(
                f"Auch pymupdf4llm-Fallback fehlgeschlagen fuer "
                f"{path.name}: {exc}"
            ) from exc

        extracted = ExtractedDoc(
            source=str(path),
            source_type="pdf",
            title=path.stem,
            body_md=body_md,
            tables=[],  # pymupdf4llm rendert Tabellen inline im Markdown
            page_count=page_count,
            language="de",
            meta={
                **_build_meta(path),
                "extraction_backend": "pymupdf4llm",
            },
        )

        logger.info(
            "pymupdf4llm_fallback_done",
            path=str(path),
            pages=page_count,
            md_chars=len(body_md),
        )
        return extracted

    def _get_converter(
        self, *, do_ocr: bool | None = None,
    ) -> DocumentConverter:
        """Erstellt oder gibt den gecachten DocumentConverter zurueck.

        Args:
            do_ocr: OCR-Override. Bei None wird der gecachte Converter
                    mit Config-Default verwendet. Bei explizitem Wert
                    wird ein frischer Converter erstellt (nicht gecacht).
        """
        if do_ocr is not None and do_ocr != self._settings.docling_ocr:
            # Per-Dokument-Override: frischer Converter (nicht cachen)
            return _build_converter(self._settings, do_ocr_override=do_ocr)
        if self._converter is None:
            self._converter = _build_converter(self._settings)
        return self._converter


# -- module-level helpers -------------------------------------------------


def _check_conversion_integrity(result: Any, path: Path) -> None:
    """Prueft ob die Docling-Konvertierung vollstaendig war.

    Wirft ``PartialExtractionError`` wenn zu viele Seiten verloren gingen.

    Args:
        result: Docling ConversionResult.
        path: Original-Dateipfad (fuer Logging).

    Raises:
        PartialExtractionError: Seitenverlust ueber Schwelle.
    """
    failed_count = len(result.errors)
    ok_count = len(result.pages)
    total = failed_count + ok_count

    if failed_count == 0:
        return

    # Immer loggen wenn Fehler auftreten
    error_details = [
        {
            "page": getattr(e, "page_no", "?"),
            "category": str(getattr(e, "category", "?")),
            "msg": getattr(e, "error_message", str(e)),
        }
        for e in result.errors[:10]
    ]
    logger.warning(
        "docling_page_errors",
        path=str(path),
        status=str(result.status),
        failed=failed_count,
        total=total,
        errors=error_details,
    )

    if total > 0 and failed_count / total > _MAX_PAGE_LOSS_RATIO:
        raise PartialExtractionError(
            f"Docling verlor {failed_count}/{total} Seiten bei "
            f"{path.name} (Status: {result.status})",
            failed_pages=failed_count,
            total_pages=total,
        )

    # Status FAILURE auch ohne einzelne Seitenfehler abfangen
    if result.status == ConversionStatus.FAILURE:
        raise PartialExtractionError(
            f"Docling meldet FAILURE fuer {path.name}",
            failed_pages=failed_count,
            total_pages=total,
        )


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


def _build_converter(
    settings: Settings,
    *,
    do_ocr_override: bool | None = None,
) -> DocumentConverter:
    """Erstellt einen Docling DocumentConverter aus den Settings.

    Args:
        settings: Typisierte Laufzeit-Konfiguration.
        do_ocr_override: Ueberschreibt ``settings.docling_ocr`` wenn gesetzt.

    Returns:
        Konfigurierter DocumentConverter.
    """
    table_mode = (
        TableFormerMode.ACCURATE
        if settings.docling_table_mode == "accurate"
        else TableFormerMode.FAST
    )
    do_ocr = do_ocr_override if do_ocr_override is not None else settings.docling_ocr
    pipeline_options = PdfPipelineOptions(
        do_table_structure=True,
        table_structure_options=TableStructureOptions(mode=table_mode),
        do_ocr=do_ocr,
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


def _compute_path_hash(path: Path) -> str:
    """Berechnet SHA256-Hash einer Datei (16 Zeichen, fuer Verzeichnisnamen)."""
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()[:16]


def _extract_figures(
    docling_doc: Any,
    source_hash: str,
    settings: Settings,
) -> list[FigureBlock]:
    """Extrahiert Abbildungen aus dem Docling-Dokument und speichert als PNG.

    Docling-Dokumente mit ``generate_picture_images=True`` enthalten
    ``pictures``-Items mit PIL-Images. Diese werden als PNG unter
    ``{figures_dir}/{source_hash}/fig_{index:03d}.png`` gespeichert.

    Args:
        docling_doc: Das konvertierte Docling-Dokument.
        source_hash: Hash der Quelldatei (fuer Verzeichnisname).
        settings: Settings-Instanz (fuer figures_dir).

    Returns:
        Liste von FigureBlock-Objekten.
    """
    pictures = getattr(docling_doc, "pictures", [])
    if not pictures:
        return []

    fig_dir = Path(settings.figures_dir) / source_hash
    fig_dir.mkdir(parents=True, exist_ok=True)

    figures: list[FigureBlock] = []
    for idx, pic in enumerate(pictures):
        image = getattr(pic, "image", None)
        if image is None:
            continue
        filename = f"fig_{idx:03d}.png"
        img_path = fig_dir / filename
        try:
            image.save(str(img_path), format="PNG")
        except Exception as exc:
            logger.warning(
                "figure_save_failed", index=idx, error=str(exc),
            )
            continue
        page_no = _get_page_number(pic)
        caption = getattr(pic, "caption", None)
        caption_str = str(caption).strip() if caption else None
        figures.append(FigureBlock(
            image_path=str(img_path),
            page=page_no,
            caption=caption_str,
            fig_index=idx,
        ))

    logger.info(
        "figures_extracted",
        total_pictures=len(pictures),
        saved=len(figures),
        directory=str(fig_dir),
    )
    return figures


def _build_meta(path: Path) -> dict[str, str]:
    """Erzeugt Metadaten-Dict aus Dateieigenschaften."""
    stat = path.stat()
    return {
        "file_name": path.name,
        "file_size_bytes": str(stat.st_size),
    }
