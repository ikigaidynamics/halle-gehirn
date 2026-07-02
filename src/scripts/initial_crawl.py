"""Initialer Crawl: Laedt alle lokalen Dokumente + optionale Web-Quellen.

Primaer: ``data/manual/`` via ManualLoader (Docling).
Sekundaer: b-tu.de-URLs via httpx-Fetcher (nur wenn konfiguriert).

Usage:
    python -m scripts.initial_crawl [--web]
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import structlog

from halle_gehirn.extraction.docling_extractor import DoclingExtractor
from halle_gehirn.extraction.html_extractor import HtmlExtractor
from halle_gehirn.extraction.manual_loader import ManualLoader
from halle_gehirn.observability.logging_config import configure_logging

logger = structlog.get_logger(__name__)

_OUTPUT_DIR: Path = Path("data/raw")


def _save_results(docs: Sequence[object], output_dir: Path) -> None:
    """Speichert Extraction-Ergebnisse als JSON-Zusammenfassung.

    Args:
        docs: Liste extrahierter Dokumente.
        output_dir: Ausgabeverzeichnis.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "extraction_summary.json"

    entries = []
    for doc in docs:
        entries.append({
            "title": getattr(doc, "title", ""),
            "source": getattr(doc, "source", ""),
            "source_type": getattr(doc, "source_type", ""),
            "page_count": getattr(doc, "page_count", None),
            "tables": len(getattr(doc, "tables", [])),
            "body_md_chars": len(getattr(doc, "body_md", "")),
        })

    summary_path.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("results_saved", path=str(summary_path), count=len(entries))


def main() -> None:
    """Haupteinstiegspunkt fuer den initialen Crawl."""
    parser = argparse.ArgumentParser(description="Initialer Crawl fuer Halle-Gehirn")
    parser.add_argument("--web", action="store_true", help="Auch Web-Quellen crawlen")
    parser.add_argument(
        "--manual-dir",
        type=Path,
        default=Path("data/manual"),
        help="Verzeichnis mit manuellen Dokumenten",
    )
    args = parser.parse_args()

    configure_logging(dev=True)

    logger.info("initial_crawl_start", web=args.web, manual_dir=str(args.manual_dir))

    # Primaer: Lokale Dokumente
    docling = DoclingExtractor()
    html = HtmlExtractor()
    loader = ManualLoader(
        base_dir=args.manual_dir,
        extractors={ext: docling for ext in docling.supported_extensions}
        | {ext: html for ext in html.supported_extensions},
    )
    docs = loader.load_all()
    logger.info("manual_docs_loaded", count=len(docs))

    # Sekundaer: Web-Quellen (optional)
    if args.web:
        logger.info("web_crawl_skipped", reason="Keine URLs konfiguriert")

    _save_results(docs, _OUTPUT_DIR)

    logger.info("initial_crawl_done", manual_docs=len(docs))


if __name__ == "__main__":
    main()
