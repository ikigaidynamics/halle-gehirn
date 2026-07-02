"""Reindex-Script: Fuehrt die Ingest-Pipeline aus.

Laedt Dokumente aus data/manifest.yaml, validiert, chunked, baut
Payloads und upserted in Qdrant. --reset loescht/erstellt NUR die
konfigurierte Collection (QDRANT_COLLECTION), NIEMALS andere.

Usage:
    python -m scripts.reindex [--reset] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import structlog

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.embeddings.ollama_embedder import OllamaEmbedder
from halle_gehirn.embeddings.sparse_embedder import FastEmbedSparseEmbedder
from halle_gehirn.observability.logging_config import configure_logging
from halle_gehirn.pipeline.ingest import IngestError, run_ingest
from halle_gehirn.vector_store.qdrant_client import (
    reset_collection,
    upsert_chunks,
)
from halle_gehirn.vector_store.schema import ChunkPayload

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
        asyncio.run(_embed_and_upsert(payloads, settings))


def _reset_collection(settings: Settings) -> None:
    """Setzt AUSSCHLIESSLICH die konfigurierte Collection zurueck."""
    logger.warning(
        "collection_reset_start",
        collection=settings.qdrant_collection,
    )
    reset_collection()
    logger.info(
        "collection_reset_done",
        collection=settings.qdrant_collection,
    )


async def _embed_and_upsert(
    payloads: list[ChunkPayload],
    settings: Settings,
) -> None:
    """Erzeugt Embeddings und upserted in Qdrant."""
    texts = [p.text for p in payloads]

    dense_embedder = OllamaEmbedder(settings=settings)
    sparse_embedder = FastEmbedSparseEmbedder(settings=settings)

    logger.info("embedding_start", chunks=len(texts))
    dense_vecs = await dense_embedder.embed(texts)
    sparse_vecs = sparse_embedder.embed(texts)
    logger.info("embedding_done", dense=len(dense_vecs), sparse=len(sparse_vecs))

    total = upsert_chunks(payloads, dense_vecs, sparse_vecs)
    logger.info("upsert_complete", total=total)


def _print_summary(
    stats: object,
    payloads: list[ChunkPayload],
    dry_run: bool,
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


if __name__ == "__main__":
    main()
