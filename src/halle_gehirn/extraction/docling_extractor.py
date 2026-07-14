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

import httpx
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
from halle_gehirn.extraction.boilerplate import clean as clean_boilerplate
from halle_gehirn.extraction.figure_utils import (
    extract_figures_from_serve,
    extract_figures_local,
)
from halle_gehirn.extraction.page_map import (
    build_page_map,
    join_pages_with_map,
    remove_cross_page_repeats,
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

        if self._settings.docling_serve_url:
            try:
                return self._convert_remote(path, do_ocr=do_ocr)
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                logger.warning(
                    "docling_serve_unreachable_fallback_local",
                    url=self._settings.docling_serve_url,
                    error=str(exc),
                )
                # Fall through to local Docling pipeline

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

    def _convert_remote(
        self,
        path: Path,
        *,
        do_ocr: bool | None = None,
    ) -> ExtractedDoc:
        """Sendet die Datei an Docling Serve und baut ein ExtractedDoc.

        Args:
            path: Aufgeloester Dateipfad.
            do_ocr: OCR-Override (None = Config-Default).

        Returns:
            Strukturiertes ExtractedDoc.

        Raises:
            ExtractionError: Server antwortet mit Fehler.
            httpx.ConnectError: Server nicht erreichbar (Caller faengt ab).
            httpx.TimeoutException: Timeout (Caller faengt ab).
        """
        base_url = self._settings.docling_serve_url.rstrip("/")
        ocr_flag = do_ocr if do_ocr is not None else self._settings.docling_ocr

        logger.info(
            "docling_serve_request",
            url=base_url,
            path=str(path),
            do_ocr=ocr_flag,
        )

        with httpx.Client(timeout=httpx.Timeout(600.0)) as client, path.open("rb") as f:
            resp = client.post(
                f"{base_url}/v1/convert/file",
                files=[("files", (path.name, f, "application/octet-stream"))],
                data={
                    "to_formats": ["md", "json"],
                    "do_ocr": str(ocr_flag).lower(),
                    "table_mode": self._settings.docling_table_mode,
                    "image_export_mode": "embedded",
                },
            )
        resp.raise_for_status()
        payload = resp.json()

        status = payload.get("status", "")
        errors = payload.get("errors", [])
        if status == "failure":
            raise ExtractionError(
                f"Docling Serve meldet FAILURE fuer {path.name}: {errors}"
            )

        logger.info(
            "docling_serve_response",
            status=status,
            errors=len(errors),
            processing_time=payload.get("processing_time"),
        )

        return self._build_result_from_remote(payload, path)

    def _build_result_from_remote(
        self,
        payload: dict[str, Any],
        path: Path,
    ) -> ExtractedDoc:
        """Baut ein ExtractedDoc aus der Docling-Serve-Response.

        Args:
            payload: JSON-Response von ``/v1/convert/file``.
            path: Original-Dateipfad.

        Returns:
            Fertiges ExtractedDoc.
        """
        doc = payload.get("document", {})
        body_md: str = doc.get("md_content") or ""
        jc: dict[str, Any] = doc.get("json_content") or {}

        if self._settings.boilerplate_clean:
            body_md = clean_boilerplate(body_md)

        # -- Tabellen aus json_content --
        tables: list[TableBlock] = []
        for tbl in jc.get("tables", []):
            grid = (tbl.get("data") or {}).get("grid", [])
            md = _grid_to_markdown(grid) if grid else ""
            if not md:
                continue
            prov = tbl.get("prov", [])
            page_no = prov[0]["page_no"] if prov else None
            captions = tbl.get("captions", [])
            caption_str: str | None = None
            if captions:
                ref = captions[0].get("$ref", "")
                caption_str = _resolve_ref_text(jc, ref)
            tables.append(
                TableBlock(markdown=md, page=page_no, caption=caption_str)
            )

        # -- Page-Map aus json_content texts --
        page_elements: list[tuple[str, int | None]] = []
        for txt in jc.get("texts", []):
            text = txt.get("text", "")
            if not text.strip():
                continue
            prov = txt.get("prov", [])
            pg = prov[0]["page_no"] if prov else None
            page_elements.append((text, pg))
        page_map = build_page_map(body_md, page_elements)

        # -- Metadaten --
        pages_dict = jc.get("pages", {})
        page_count = len(pages_dict) if pages_dict else None
        title = jc.get("name") or path.stem
        source_type = path.suffix.lstrip(".").lower()

        # -- Abbildungen aus json_content (embedded Base64) --
        source_hash = _compute_path_hash(path)
        figures = extract_figures_from_serve(
            jc, source_hash, self._settings,
            resolve_ref_text=_resolve_ref_text,
        )

        extracted = ExtractedDoc(
            source=str(path),
            source_type=source_type,
            title=str(title).strip(),
            body_md=body_md,
            tables=tables,
            figures=figures,
            page_count=page_count,
            language="de",
            meta={
                **_build_meta(path),
                "extraction_backend": "docling_serve",
                "docling_serve_url": self._settings.docling_serve_url,
            },
            page_map=page_map,
        )
        logger.info(
            "docling_serve_extraction_done",
            path=str(path),
            pages=page_count,
            tables=len(tables),
            figures=len(figures),
            md_chars=len(body_md),
            page_map_entries=len(page_map),
        )
        return extracted

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
        if self._settings.boilerplate_clean:
            body_md = clean_boilerplate(body_md)
        # Page-Map NACH dem Cleaning bauen (Offsets muessen zum finalen
        # Body passen; entfernte Kopf-/Fusszeilen-Elemente matchen nicht)
        page_map = build_page_map(body_md, _page_elements(docling_doc))
        tables = _extract_tables(docling_doc)
        source_hash = _compute_path_hash(path)
        figures = extract_figures_local(
            docling_doc, source_hash, self._settings,
            get_page_number=_get_page_number,
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
            page_map=page_map,
        )
        logger.info(
            "docling_extraction_done",
            path=str(path),
            pages=page_count,
            tables=len(tables),
            figures=len(figures),
            md_chars=len(body_md),
            page_map_entries=len(page_map),
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
            # page_chunks=True liefert Markdown JE SEITE → exakte Page-Map
            page_dicts: list[dict[str, Any]] = pymupdf4llm.to_markdown(
                str(path), show_progress=False, page_chunks=True,
            )
            pages = [str(p.get("text", "")) for p in page_dicts]
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

        if self._settings.boilerplate_clean:
            # Kopf-/Fusszeilen wiederholen sich je Seite — erst ueber
            # alle Seiten zaehlen, dann seitenweise bereinigen
            pages = remove_cross_page_repeats(pages)
            pages = [clean_boilerplate(p) for p in pages]
        body_md, page_map = join_pages_with_map(pages)

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
            page_map=page_map,
        )

        logger.info(
            "pymupdf4llm_fallback_done",
            path=str(path),
            pages=page_count,
            md_chars=len(body_md),
            page_map_entries=len(page_map),
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


def _cell_text(cell: Any) -> str:
    """Extrahiert den Textinhalt einer Tabellenzelle.

    Unterstuetzt sowohl Docling-Objekte (lokale Lib) als auch
    dicts aus der JSON-API-Response.
    """
    if isinstance(cell, dict):
        return str(cell.get("text", ""))
    return str(cell)


def _grid_to_markdown(grid: list[list[Any]]) -> str:
    """Konvertiert ein Docling-Tabellen-Grid zu Markdown-Tabelle."""
    if not grid:
        return ""
    lines: list[str] = []
    header = [_cell_text(c) for c in grid[0]]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in grid[1:]:
        cells = [_cell_text(c) for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    return chr(10).join(lines)


def _get_page_number(element: Any) -> int | None:
    """Liest die Seitennummer aus einem Docling-Element."""
    prov = getattr(element, "prov", None)
    if prov and len(prov) > 0:
        return getattr(prov[0], "page_no", None)
    return None


def _page_elements(docling_doc: Any) -> list[tuple[str, int | None]]:
    """Extrahiert (text, page_no) je Text-Element in Dokumentreihenfolge.

    Grundlage fuer ``build_page_map`` — Tabellen/Bilder tragen ihre
    Seite bereits selbst (TableBlock/FigureBlock).
    """
    elements: list[tuple[str, int | None]] = []
    for item in getattr(docling_doc, "texts", []):
        text = getattr(item, "text", "") or ""
        if text.strip():
            elements.append((text, _get_page_number(item)))
    return elements


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


def _resolve_ref_text(jc: dict[str, Any], ref: str) -> str | None:
    """Loest eine ``$ref`` (z.B. ``#/texts/3``) im json_content auf.

    Args:
        jc: Das json_content-Dict aus der Docling-Serve-Response.
        ref: JSON-Pointer-Referenz (z.B. ``#/texts/3``).

    Returns:
        Den ``text``-Wert des referenzierten Objekts oder None.
    """
    if not ref.startswith("#/"):
        return None
    parts = ref.lstrip("#/").split("/")
    if len(parts) != 2:
        return None
    collection, idx_str = parts
    try:
        idx = int(idx_str)
    except ValueError:
        return None
    items = jc.get(collection, [])
    if not isinstance(items, list) or idx >= len(items):
        return None
    text = items[idx].get("text", "")
    return text.strip() if text else None


def _build_meta(path: Path) -> dict[str, str]:
    """Erzeugt Metadaten-Dict aus Dateieigenschaften."""
    stat = path.stat()
    return {
        "file_name": path.name,
        "file_size_bytes": str(stat.st_size),
    }
