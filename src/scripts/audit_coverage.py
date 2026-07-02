"""Audit Coverage: Prueft welche Dateien in data/manual/ erfolgreich extrahiert werden.

Zeigt eine Uebersicht ueber Erfolge, Fehler und fehlende Dateien.
Hilfreich fuer die Qualitaetssicherung der Extraction-Pipeline.

Usage:
    python -m scripts.audit_coverage [--manual-dir data/manual]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import structlog

from halle_gehirn.extraction.base import ExtractionError
from halle_gehirn.extraction.docling_extractor import DoclingExtractor
from halle_gehirn.observability.logging_config import configure_logging

logger = structlog.get_logger(__name__)

_SUPPORTED_SUFFIXES: frozenset[str] = frozenset(
    {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm",
     ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
)


def audit_coverage(base_dir: Path) -> dict[str, list[str]]:
    """Prueft Extraction-Coverage ueber alle Dateien.

    Args:
        base_dir: Basisverzeichnis (z.B. data/manual/).

    Returns:
        Dict mit Listen: 'success', 'failed', 'unsupported', 'empty'.
    """
    result: dict[str, list[str]] = {
        "success": [],
        "failed": [],
        "unsupported": [],
        "empty": [],
    }

    if not base_dir.exists():
        logger.error("audit_dir_missing", path=str(base_dir))
        return result

    extractor = DoclingExtractor()
    files = sorted(p for p in base_dir.rglob("*") if p.is_file())
    logger.info("audit_coverage_start", file_count=len(files))

    for path in files:
        rel = str(path.relative_to(base_dir))

        if path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            result["unsupported"].append(rel)
            continue

        try:
            doc = extractor.extract(path)
            if not doc.body_md.strip():
                result["empty"].append(rel)
            else:
                result["success"].append(rel)
        except ExtractionError as exc:
            result["failed"].append(f"{rel}: {exc}")
            logger.warning("audit_extraction_failed", path=rel, error=str(exc))

    logger.info(
        "audit_coverage_done",
        success=len(result["success"]),
        failed=len(result["failed"]),
        unsupported=len(result["unsupported"]),
        empty=len(result["empty"]),
    )
    return result


def main() -> None:
    """Haupteinstiegspunkt fuer das Coverage-Audit."""
    parser = argparse.ArgumentParser(description="Extraction-Coverage-Audit")
    parser.add_argument(
        "--manual-dir",
        type=Path,
        default=Path("data/manual"),
        help="Verzeichnis mit Dokumenten",
    )
    args = parser.parse_args()

    configure_logging(dev=True)
    results = audit_coverage(args.manual_dir)

    print(f"\n{'='*60}")
    print("EXTRACTION COVERAGE AUDIT")
    print(f"{'='*60}")
    print(f"  Erfolgreich:   {len(results['success'])}")
    print(f"  Fehlgeschlagen: {len(results['failed'])}")
    print(f"  Leer:          {len(results['empty'])}")
    print(f"  Nicht unterstuetzt: {len(results['unsupported'])}")
    print(f"{'='*60}")

    if results["failed"]:
        print("\nFehlgeschlagen:")
        for item in results["failed"]:
            print(f"  - {item}")

    if results["empty"]:
        print("\nLeer (kein Markdown-Inhalt):")
        for item in results["empty"]:
            print(f"  - {item}")


if __name__ == "__main__":
    main()
