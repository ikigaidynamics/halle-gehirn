"""Audit Content: Prueft Qualitaet der extrahierten Inhalte.

Analysiert Markdown-Ergebnisse auf Laenge, Tabellen-Praesenz,
Boilerplate-Anteil und Titel-Qualitaet. Erstellt einen Report.

Usage:
    python -m scripts.audit_content [--manual-dir data/manual]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import structlog

from halle_gehirn.extraction.base import ExtractionError
from halle_gehirn.extraction.boilerplate import clean
from halle_gehirn.extraction.docling_extractor import DoclingExtractor
from halle_gehirn.observability.logging_config import configure_logging

logger = structlog.get_logger(__name__)

_SUPPORTED_SUFFIXES: frozenset[str] = frozenset(
    {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm",
     ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
)


def audit_content(base_dir: Path) -> list[dict[str, object]]:
    """Analysiert Qualitaet der extrahierten Inhalte.

    Args:
        base_dir: Basisverzeichnis mit Quelldateien.

    Returns:
        Liste mit Qualitaets-Reports je Datei.
    """
    reports: list[dict[str, object]] = []

    if not base_dir.exists():
        logger.error("audit_dir_missing", path=str(base_dir))
        return reports

    extractor = DoclingExtractor()
    files = sorted(
        p for p in base_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in _SUPPORTED_SUFFIXES
    )

    logger.info("audit_content_start", file_count=len(files))

    for path in files:
        rel = str(path.relative_to(base_dir))
        try:
            doc = extractor.extract(path)
            cleaned = clean(doc.body_md)
            boilerplate_chars = len(doc.body_md) - len(cleaned)
            reports.append({
                "file": rel,
                "title": doc.title,
                "md_chars": len(doc.body_md),
                "boilerplate_chars": boilerplate_chars,
                "page_count": doc.page_count,
                "tables": len(doc.tables),
                "source_type": doc.source_type,
            })
        except ExtractionError as exc:
            reports.append({
                "file": rel,
                "error": str(exc),
            })

    logger.info("audit_content_done", file_count=len(reports))
    return reports


def main() -> None:
    """Haupteinstiegspunkt fuer das Content-Audit."""
    parser = argparse.ArgumentParser(description="Content-Qualitaets-Audit")
    parser.add_argument(
        "--manual-dir",
        type=Path,
        default=Path("data/manual"),
        help="Verzeichnis mit Dokumenten",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Ausgabe als JSON-Datei",
    )
    args = parser.parse_args()

    configure_logging(dev=True)
    reports = audit_content(args.manual_dir)

    print(f"\n{'='*60}")
    print("CONTENT QUALITY AUDIT")
    print(f"{'='*60}")

    for r in reports:
        if "error" in r:
            print(f"  FEHLER {r['file']}: {r['error']}")
            continue
        flags = []
        md_chars = r.get("md_chars", 0)
        if isinstance(md_chars, int) and md_chars < 100:
            flags.append("SEHR-KURZ")
        bp_chars = r.get("boilerplate_chars", 0)
        if isinstance(bp_chars, int) and bp_chars > 500:
            flags.append("BOILERPLATE")
        status = " [" + ", ".join(flags) + "]" if flags else ""
        print(
            f"  {r['file']}: {r['md_chars']} Zeichen, "
            f"{r['tables']} Tabellen{status}"
        )

    print(f"{'='*60}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(reports, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Report gespeichert: {args.output}")


if __name__ == "__main__":
    main()
