"""Laedt kuratierte Dokumente aus ``data/manual/``.

Iteriert ueber die Unterverzeichnisse (abschlussarbeiten, projektberichte,
transfer, anlagen, transkripte) und dispatcht jede Datei an den passenden
Extractor (Docling fuer PDF/DOCX/PPTX/XLSX, HTML-Extractor fuer HTML).
Primaerquelle fuer Halle-Gehirn -- der Crawler ist nur sekundaer.

Kurations-Metadaten werden aus ``data/manifest.yaml`` gelesen und in die
``ExtractedDoc.meta``-Felder uebernommen.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

from halle_gehirn.extraction.base import (
    ExtractedDoc,
    ExtractionError,
    Extractor,
)

logger = structlog.get_logger(__name__)

# Erwartete Unterverzeichnisse in data/manual/
_EXPECTED_SUBDIRS: tuple[str, ...] = (
    "abschlussarbeiten",
    "projektberichte",
    "transfer",
    "anlagen",
    "transkripte",
)

# Manifest-Pfad relativ zum Projekt (Geschwister von manual/)
_MANIFEST_FILENAME: str = "manifest.yaml"


class ManualLoader:
    """Laedt und extrahiert alle Dokumente aus dem manuellen Verzeichnis.

    Dispatcht Dateien anhand ihrer Endung an den passenden Extractor
    und reichert die Ergebnisse mit Kurations-Metadaten aus dem Manifest an.

    Args:
        base_dir: Basisverzeichnis mit den Dokumenten (z.B. data/manual/).
        extractors: Mapping von Dateiendung (z.B. ".pdf") zu Extractor-Instanz.
    """

    def __init__(
        self,
        base_dir: Path,
        extractors: dict[str, Extractor],
    ) -> None:
        self._base_dir = base_dir
        self._extractors = extractors
        self._supported: frozenset[str] = frozenset(extractors.keys())

    # ------------------------------------------------------------------
    # Oeffentliche API
    # ------------------------------------------------------------------

    def discover(self) -> list[Path]:
        """Findet alle verarbeitbaren Dateien in base_dir rekursiv.

        Durchsucht das gesamte Verzeichnis und filtert nach Dateien,
        deren Endung von einem registrierten Extractor unterstuetzt wird.

        Returns:
            Sortierte Liste der gefundenen Dateipfade.
        """
        if not self._base_dir.exists():
            logger.warning("manual_dir_missing", path=str(self._base_dir))
            return []

        files: list[Path] = []
        for path in sorted(self._base_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue
            if path.suffix.lower() in self._supported:
                files.append(path)

        logger.info(
            "manual_discover_done",
            base_dir=str(self._base_dir),
            file_count=len(files),
        )
        return files

    def load_manifest(self) -> dict[str, dict[str, Any]]:
        """Laedt Kurations-Metadaten aus data/manifest.yaml.

        Das Manifest liegt als Geschwister-Verzeichnis neben manual/,
        also unter ``base_dir.parent / manifest.yaml``.

        Returns:
            Mapping von relativem Dateipfad zu Metadaten-Dict.
            Leeres Dict, wenn das Manifest fehlt oder ungueltig ist.
        """
        manifest_path = self._base_dir.parent / _MANIFEST_FILENAME

        if not manifest_path.exists():
            logger.info("manifest_not_found", path=str(manifest_path))
            return {}

        try:
            raw = manifest_path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw)
        except (yaml.YAMLError, OSError) as exc:
            logger.warning(
                "manifest_load_failed",
                path=str(manifest_path),
                error=str(exc),
            )
            return {}

        if not isinstance(data, dict):
            logger.warning("manifest_invalid_format", path=str(manifest_path))
            return {}

        return _parse_manifest(data)

    def load_all(self) -> list[ExtractedDoc]:
        """Entdeckt Dateien, extrahiert sie und reichert mit Manifest an.

        Fuer jede Datei wird der passende Extractor aufgerufen. Fehler bei
        einzelnen Dateien werden geloggt, aber uebersprungen (fail-forward).
        Manifest-Metadaten werden in ``ExtractedDoc.meta`` gemergt.

        Per-Dokument-OCR-Steuerung: Enthaelt das Manifest ein Feld
        ``do_ocr: false`` fuer eine Datei, wird dieses an den Extractor
        durchgereicht (sofern dieser das unterstuetzt).

        Returns:
            Liste erfolgreich extrahierter Dokumente.
        """
        files = self.discover()
        manifest = self.load_manifest()

        logger.info(
            "manual_load_all_start",
            file_count=len(files),
            manifest_entries=len(manifest),
        )

        docs: list[ExtractedDoc] = []
        errors: list[str] = []

        for path in files:
            ocr_override = self._get_ocr_override(path, manifest)
            doc = self._extract_single(path, do_ocr=ocr_override)
            if doc is None:
                errors.append(path.name)
                continue

            self._enrich_from_manifest(doc, path, manifest)
            self._enrich_breadcrumb(doc, path)
            docs.append(doc)

        # Gescheiterte Dokumente auf WARNING heben, damit stille
        # Totalverluste nicht im INFO-Rauschen untergehen (fail-forward,
        # aber sichtbar). Der Haupt-Ingest-Pfad (ingest.run_ingest)
        # zaehlt Failures zusaetzlich in IngestStats.
        log = logger.warning if errors else logger.info
        log(
            "manual_load_all_done",
            loaded=len(docs),
            failed=len(errors),
            errors=errors[:10] if errors else [],
        )
        return docs

    # ------------------------------------------------------------------
    # Interne Helfer
    # ------------------------------------------------------------------

    def _extract_single(
        self,
        path: Path,
        *,
        do_ocr: bool | None = None,
    ) -> ExtractedDoc | None:
        """Extrahiert eine einzelne Datei mit dem passenden Extractor.

        Args:
            path: Dateipfad.
            do_ocr: OCR-Override aus dem Manifest (None = Extractor-Default).

        Returns:
            ExtractedDoc oder None bei Fehler.
        """
        suffix = path.suffix.lower()
        extractor = self._extractors.get(suffix)

        if extractor is None:
            logger.warning("manual_no_extractor", path=str(path), suffix=suffix)
            return None

        try:
            # do_ocr-Override durchreichen (sofern der Extractor es akzeptiert)
            if do_ocr is not None and hasattr(extractor.extract, "__code__"):
                import inspect
                sig = inspect.signature(extractor.extract)
                if "do_ocr" in sig.parameters:
                    doc = extractor.extract(path, do_ocr=do_ocr)
                else:
                    doc = extractor.extract(path)
            else:
                doc = extractor.extract(path)
            logger.info(
                "manual_doc_extracted",
                path=str(path),
                title=doc.title,
            )
            return doc
        except ExtractionError as exc:
            logger.warning(
                "manual_extraction_failed",
                path=str(path),
                error=str(exc),
            )
            return None
        except Exception as exc:
            logger.error(
                "manual_extraction_unexpected",
                path=str(path),
                error=str(exc),
            )
            return None

    def _get_ocr_override(
        self,
        path: Path,
        manifest: dict[str, dict[str, Any]],
    ) -> bool | None:
        """Liest den do_ocr-Override aus dem Manifest fuer eine Datei.

        Args:
            path: Dateipfad.
            manifest: Geparstes Manifest.

        Returns:
            True/False wenn im Manifest gesetzt, sonst None.
        """
        try:
            rel_path = path.relative_to(self._base_dir).as_posix()
        except ValueError:
            return None

        entry = manifest.get(rel_path)
        if entry is None:
            return None

        do_ocr = entry.get("do_ocr")
        if isinstance(do_ocr, bool):
            return do_ocr
        return None

    def _enrich_from_manifest(
        self,
        doc: ExtractedDoc,
        path: Path,
        manifest: dict[str, dict[str, Any]],
    ) -> None:
        """Reichert ein ExtractedDoc mit Manifest-Metadaten an.

        Sucht den relativen Pfad der Datei im Manifest und kopiert
        alle gefundenen Felder in ``doc.meta``.

        Args:
            doc: Das anzureichernde Dokument.
            path: Absoluter Dateipfad.
            manifest: Geparstes Manifest (relative Pfade -> Metadaten).
        """
        try:
            rel_path = path.relative_to(self._base_dir)
        except ValueError:
            return

        rel_key = rel_path.as_posix()
        entry = manifest.get(rel_key)
        if entry is None:
            logger.debug("manifest_no_entry", file=rel_key)
            return

        for key, value in entry.items():
            doc.meta[key] = str(value) if not isinstance(value, str) else value

        if entry.get("titel"):
            doc.title = str(entry["titel"])

        logger.debug("manifest_enriched", file=rel_key, fields=list(entry.keys()))

    def _enrich_breadcrumb(self, doc: ExtractedDoc, path: Path) -> None:
        """Leitet einen Breadcrumb aus der Verzeichnisstruktur ab.

        Setzt ``doc.meta["breadcrumb"]`` auf den relativen Pfad der
        uebergeordneten Verzeichnisse (z.B. "anlagen > handbuecher").

        Args:
            doc: Das anzureichernde Dokument.
            path: Absoluter Dateipfad.
        """
        try:
            rel = path.relative_to(self._base_dir)
        except ValueError:
            return

        if len(rel.parts) > 1:
            doc.meta["breadcrumb"] = " > ".join(rel.parts[:-1])


def _parse_manifest(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Wandelt die YAML-Struktur in ein Pfad-zu-Metadaten-Mapping um.

    Das Manifest hat die Struktur::

        dokumente:
          - datei: "abschlussarbeiten/foo.pdf"
            titel: "..."
            doc_type: abschlussarbeit
            ...

    Args:
        data: Geparstes YAML-Dict.

    Returns:
        Mapping von relativem Dateipfad zu den restlichen Metadaten.
    """
    result: dict[str, dict[str, Any]] = {}
    dokumente = data.get("dokumente", [])

    if not isinstance(dokumente, list):
        logger.warning("manifest_dokumente_not_list")
        return result

    for entry in dokumente:
        if not isinstance(entry, dict):
            continue
        datei = entry.get("datei")
        if not datei or not isinstance(datei, str):
            continue
        meta = {k: v for k, v in entry.items() if k != "datei"}
        result[datei] = meta

    logger.info("manifest_parsed", entries=len(result))
    return result
