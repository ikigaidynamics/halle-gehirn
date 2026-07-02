"""Trafilatura-basierter HTML-Extractor fuer die Extraction-Schicht.

Nutzt Trafilatura fuer saubere Textextraktion aus HTML-Dateien und URLs.
Implementiert das Extractor-Protocol aus extraction/base.py und liefert
ExtractedDoc mit source_type="html".
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import httpx
import structlog
import trafilatura

from halle_gehirn.config import get_settings
from halle_gehirn.extraction.base import (
    ExtractedDoc,
    ExtractionError,
    TableBlock,
)

logger = structlog.get_logger(__name__)

_SUPPORTED: frozenset[str] = frozenset({".html", ".htm"})

_TITLE_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.IGNORECASE)


def _is_url(source: str) -> bool:
    """Prueft ob der String eine HTTP(S)-URL ist."""
    return source.startswith(("http://", "https://"))


def _fetch_url(url: str, *, timeout: float = 30.0) -> str:
    """Laedt HTML-Inhalt von einer URL via httpx.

    Args:
        url: Ziel-URL.
        timeout: Request-Timeout in Sekunden.

    Returns:
        HTML-Inhalt als String.

    Raises:
        ExtractionError: HTTP-Fehler oder Netzwerkproblem.
    """
    logger.info("html_fetch_start", url=url)
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ExtractionError(
            f"HTML-Fetch fehlgeschlagen fuer {url}: {exc}"
        ) from exc
    return response.text


def _read_file(path: Path) -> str:
    """Liest eine lokale HTML-Datei.

    Args:
        path: Pfad zur HTML-Datei.

    Returns:
        Dateiinhalt als String.

    Raises:
        ExtractionError: Datei nicht gefunden oder nicht lesbar.
    """
    if not path.exists():
        raise ExtractionError(f"HTML-Datei nicht gefunden: {path}")
    if not path.is_file():
        raise ExtractionError(f"Kein regulaeres File: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def _extract_title_fallback(html: str) -> str:
    """Extrahiert den Titel aus einem <title>-Tag als Fallback."""
    match = _TITLE_RE.search(html)
    if match:
        return match.group(1).strip()
    return ""


def _extract_metadata_title(html: str, url: str) -> str:
    """Extrahiert den Dokumenttitel via Trafilatura-Metadaten.

    Nutzt trafilatura.extract_metadata fuer den Titel. Bei Fehlen
    wird auf den <title>-Tag zurueckgegriffen.

    Args:
        html: Roher HTML-String.
        url: Herkunfts-URL (fuer Metadaten-Kontext).

    Returns:
        Dokumenttitel oder Fallback.
    """
    try:
        metadata = trafilatura.extract_metadata(html, default_url=url)
        if metadata:
            title: str | None = getattr(metadata, "title", None)
            if title and title.strip():
                return title.strip()
    except Exception:
        logger.debug("metadata_extraction_failed", url=url)
    return _extract_title_fallback(html)


def _source_label(source: str | Path) -> str:
    """Erzeugt ein lesbares Label fuer Logging und Fallback-Titel."""
    if isinstance(source, Path):
        return source.stem
    parsed = urlparse(source)
    return parsed.netloc + parsed.path if parsed.netloc else str(source)


class HtmlExtractor:
    """Trafilatura-basierter Extractor fuer HTML-Dateien und URLs.

    Implementiert das Extractor-Protocol aus extraction/base.py.
    Unterstuetzt .html und .htm Dateien sowie HTTP(S)-URLs.
    """

    def __init__(self) -> None:
        """Initialisiert den HtmlExtractor mit Settings."""
        self._settings = get_settings()
        logger.info("html_extractor_initialized")

    @property
    def supported_extensions(self) -> frozenset[str]:
        """Dateiendungen, die dieser Extractor verarbeitet."""
        return _SUPPORTED

    def extract(self, source: str | Path) -> ExtractedDoc:
        """Extrahiert sauberen Text aus einer HTML-Quelle.

        Liest die Quelle (Datei oder URL), nutzt Trafilatura fuer die
        Hauptinhalt-Extraktion und liefert ein ExtractedDoc zurueck.

        Args:
            source: Dateipfad (Path) oder URL-String (http/https).

        Returns:
            ExtractedDoc mit source_type="html".

        Raises:
            ExtractionError: Inhalt nicht extrahierbar.
        """
        source_str = str(source)
        label = _source_label(source)
        logger.info("html_extraction_start", source=source_str)

        html = self._load_html(source)
        body_md = self._run_trafilatura(html, source_str)
        title = _extract_metadata_title(html, source_str) or label
        tables = self._extract_tables(html, source_str)

        doc = ExtractedDoc(
            source=source_str,
            source_type="html",
            title=title,
            body_md=body_md,
            tables=tables,
            language=self._settings.language,
        )

        logger.info(
            "html_extraction_done",
            source=source_str,
            title=title,
            body_chars=len(body_md),
            table_count=len(tables),
        )
        return doc

    def _load_html(self, source: str | Path) -> str:
        """Laedt HTML-Inhalt aus Datei oder URL.

        Args:
            source: Dateipfad oder URL.

        Returns:
            Roher HTML-String.

        Raises:
            ExtractionError: Quelle nicht lesbar.
        """
        if isinstance(source, Path):
            return _read_file(source)
        if _is_url(source):
            return _fetch_url(source)
        path = Path(source)
        if path.exists():
            return _read_file(path)
        raise ExtractionError(f"Quelle weder Datei noch URL: {source}")

    def _run_trafilatura(self, html: str, source: str) -> str:
        """Fuehrt Trafilatura-Extraktion aus.

        Args:
            html: Roher HTML-String.
            source: Quellbezeichnung fuer Fehlermeldungen.

        Returns:
            Extrahierter Klartext.

        Raises:
            ExtractionError: Kein Inhalt extrahierbar.
        """
        text = trafilatura.extract(
            html,
            include_tables=True,
            include_links=True,
            output_format="txt",
            favor_precision=True,
        )

        if not text or not text.strip():
            md_text = trafilatura.extract(
                html,
                include_tables=True,
                include_links=True,
                output_format="markdown",
            )
            if md_text and md_text.strip():
                return md_text.strip()
            raise ExtractionError(
                f"Trafilatura konnte keinen Inhalt extrahieren: {source}"
            )
        return text.strip()

    def _extract_tables(self, html: str, source: str) -> list[TableBlock]:
        """Extrahiert Markdown-Tabellen aus dem Trafilatura-Output.

        Args:
            html: Roher HTML-String.
            source: Quellbezeichnung fuer Logging.

        Returns:
            Liste von TableBlock-Objekten (kann leer sein).
        """
        tables: list[TableBlock] = []
        try:
            md_output = trafilatura.extract(
                html,
                include_tables=True,
                include_links=False,
                output_format="markdown",
            )
            if not md_output:
                return tables
            tables = self._parse_md_tables(md_output)
        except Exception:
            logger.debug("table_extraction_failed", source=source)
        return tables

    @staticmethod
    def _parse_md_tables(md_output: str) -> list[TableBlock]:
        """Parst Markdown-Tabellen aus einem Markdown-String.

        Args:
            md_output: Markdown-formatierter Text.

        Returns:
            Liste von TableBlock mit je einer Tabelle.
        """
        tables: list[TableBlock] = []
        in_table = False
        current_lines: list[str] = []
        for line in md_output.splitlines():
            stripped = line.strip()
            is_table_line = stripped.startswith("|") and "|" in stripped[1:]
            if is_table_line:
                in_table = True
                current_lines.append(line)
            elif in_table:
                if current_lines:
                    tables.append(TableBlock(
                        markdown="\n".join(current_lines),
                    ))
                current_lines = []
                in_table = False
        if current_lines:
            tables.append(TableBlock(
                markdown="\n".join(current_lines),
            ))
        return tables
