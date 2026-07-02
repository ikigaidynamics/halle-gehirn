"""Reindex-Script: Fuehrt die Ingest-Pipeline aus.

Laedt Dokumente aus data/manifest.yaml, validiert, chunked, baut
Payloads und (optional in Phase 3) upserted in Qdrant.

Usage:
    python -m scripts.reindex [--reset] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import structlog

from halle_gehirn.config import get_settings
from halle_gehirn.observability.logging_config import configure_logging
from halle_gehirn.pipeline.ingest import IngestError, run_ingest

logger = structlog.get_logger(__name__)


def main() -> None:
    """Haupteinstiegspunkt fuer das Reindex-Script."""
    parser = argparse.ArgumentParser(
        description="Reindex: Ingest-Pipeline fuer Halle-Gehirn",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Qdrant-Collection zuruecksetzen (nur konfigurierte Collection)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur validieren und chunken, keine Embeddings/Upsert",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Pfad zur manifest.yaml (Default: data/manifest.yaml)",
    )
    parser.add_argument(
        "--manual-dir",
        type=Path,
        default=None,
        help="Basisverzeichnis fuer Dokumente (Default: data/manual)",
    )
    args = parser.parse_args()

    configure_logging(dev=True)
    settings = get_settings()

    if args.reset:
        _reset_collection(settings)

    try:
        payloads, stats = run_ingest(
            manifest_path=args.manifest,
            manual_dir=args.manual_dir,
            settings=settings,
        )
    except IngestError as exc:
        logger.error("ingest_aborted", error=str(exc))
        raise SystemExit(1) from exc

    _print_summary(stats, payloads, args.dry_run)

    if payloads and not args.dry_run:
        _save_payloads(payloads)


def _reset_collection(settings: object) -> None:
    """Setzt die Qdrant-Collection zurueck (nur konfigurierte)."""
    collection = getattr(settings, "qdrant_collection", "halle_wissen")
    logger.warning(
        "collection_reset_requested",
        collection=collection,
        note="Qdrant-Reset wird in Phase 3 implementiert",
    )


def _print_summary(
    stats: object, payloads: Sequence[object], dry_run: bool,
) -> None:
    """Gibt eine Zusammenfassung des Ingest-Laufs aus."""
    logger.info(
        "reindex_summary",
        docs_total=getattr(stats, "docs_total", 0),
        docs_success=getattr(stats, "docs_success", 0),
        docs_skipped=getattr(stats, "docs_skipped", 0),
        docs_failed=getattr(stats, "docs_failed", 0),
        chunks_total=getattr(stats, "chunks_total", 0),
        payloads=len(payloads),
        dry_run=dry_run,
    )
    errors = getattr(stats, "errors", [])
    if errors:
        for err in errors:
            logger.warning("reindex_error", error=err)


def _save_payloads(payloads: Sequence[object]) -> None:
    """Speichert Payloads als JSON (Debug/Verification)."""
    out = Path("data/raw/ingest_payloads.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    for p in payloads:
        if hasattr(p, "model_dump"):
            entries.append(p.model_dump())
        else:
            entries.append(str(p))
    out.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    logger.info("payloads_saved", path=str(out), count=len(entries))


if __name__ == "__main__":
    main()
