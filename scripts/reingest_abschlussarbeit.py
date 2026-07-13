"""Re-Ingest der Abschlussarbeit mit lokalem Ollama.

Setzt OLLAMA_URL auf localhost (Uni-Server unerreichbar),
ingestet nur die Abschlussarbeit Zhili Wang, zeigt Chunk-Count vorher/nachher.
"""
from __future__ import annotations

import asyncio
import os
import sys

# OLLAMA_URL auf lokal setzen BEVOR Settings initialisiert werden
os.environ["OLLAMA_URL"] = "http://localhost:11434"

from pathlib import Path

# Projekt-Root als CWD setzen (fuer data/ Pfade)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import structlog
from halle_gehirn.config import get_settings
from halle_gehirn.observability.logging_config import configure_logging
from halle_gehirn.pipeline.indexer import embed_and_upsert
from halle_gehirn.pipeline.ingest import run_ingest
from halle_gehirn.vector_store.qdrant_client import (
    delete_by_source_hash,
    get_qdrant_client,
    list_indexed_documents,
)

configure_logging(dev=True)
logger = structlog.get_logger(__name__)


def count_total_chunks() -> int:
    """Zaehlt alle Chunks in der Collection."""
    client = get_qdrant_client()
    settings = get_settings()
    if not client.collection_exists(settings.qdrant_collection):
        return 0
    info = client.get_collection(settings.qdrant_collection)
    return info.points_count or 0


def show_state(label: str) -> None:
    """Zeigt den aktuellen Zustand der Collection."""
    total = count_total_chunks()
    docs = list_indexed_documents()
    print(f"\n=== {label} ===")
    print(f"Total chunks: {total}")
    print(f"Dokumente: {len(docs)}")
    for doc in docs:
        print(f"  {doc['datei']}: {doc['chunk_count']} chunks (hash: {doc['source_hash'][:12]})")


async def main() -> None:
    settings = get_settings()
    print(f"OLLAMA_URL: {settings.ollama_url}")
    print(f"QDRANT_URL: {settings.qdrant_url}")

    # Zustand vorher
    show_state("VOR Re-Ingest")

    # Alte Chunks der Abschlussarbeit loeschen
    target = "abschlussarbeiten/Abschlussarbeit_Zhili Wang.pdf"
    old_hash = "be25242d22f14a644e18fa31dec931c22120fd95bce0a728e9057601f7bd61ef"
    print(f"\nLoesche alte Chunks (hash={old_hash[:12]}...)")
    delete_by_source_hash(old_hash)

    print(f"Ingesting: {target}")

    payloads, stats = run_ingest(
        settings=settings,
        selected_dateien={target},
    )

    print(f"\nIngest-Ergebnis:")
    print(f"  docs_total: {stats.docs_total}")
    print(f"  docs_success: {stats.docs_success}")
    print(f"  docs_failed: {stats.docs_failed}")
    print(f"  chunks_total: {stats.chunks_total}")
    if stats.errors:
        for err in stats.errors:
            print(f"  ERROR: {err}")

    if not payloads:
        print("Keine Payloads erzeugt — Abbruch.")
        return

    print(f"\n{len(payloads)} Payloads erzeugt, starte Embedding + Upsert...")
    result = await embed_and_upsert(payloads, settings)
    print(f"Embedded: {result.chunks_embedded}, Upserted: {result.chunks_upserted}")

    # Zustand nachher
    show_state("NACH Re-Ingest")


if __name__ == "__main__":
    asyncio.run(main())
