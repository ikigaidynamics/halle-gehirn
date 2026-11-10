"""Voll-Re-Ingest: Reset + Extract + Chunk + Embed + Upsert.

Laeuft alle Dokumente aus manifest.yaml durch die komplette Pipeline.
Gibt am Ende eine Tabelle mit Dokument → Chunk-Count und sanitizer_stats aus.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# Projekt-Root in sys.path
_PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT / "src"))

from halle_gehirn.config import get_settings
from halle_gehirn.pipeline.ingest import run_ingest, IngestStats
from halle_gehirn.pipeline.indexer import embed_and_upsert, IndexResult
from halle_gehirn.vector_store.qdrant_client import (
    get_qdrant_client,
    reset_collection,
)


def main() -> None:
    s = get_settings()
    print(f"=== Voll-Re-Ingest auf Collection '{s.qdrant_collection}' ===")
    print(f"Ollama: {s.ollama_url}  |  LLM: {s.llm_model}")
    print(f"Embedding: {s.embedding_model}  |  Qdrant: {s.qdrant_url}")
    print(f"Docling Serve: {s.docling_serve_url or '(lokal)'}")
    print()

    # Schritt 1: Reset
    print("--- Schritt 1: Collection reset ---")
    client = get_qdrant_client()
    existing = client.collection_exists(s.qdrant_collection)
    if existing:
        info = client.get_collection(s.qdrant_collection)
        print(f"  Alter Bestand: {info.points_count} Punkte")
    reset_collection(client)
    print(f"  Collection '{s.qdrant_collection}' zurueckgesetzt.")
    print()

    # Schritt 2: Ingest (Extract + Chunk + Filter)
    print("--- Schritt 2: Extract + Chunk + Filter ---")
    t0 = time.monotonic()

    def _progress(event):
        if event.phase == "extract":
            print(f"  [{event.doc_index}/{event.doc_total}] Extrahiere {event.datei}...")
        elif event.phase == "chunk":
            be = ""
            if hasattr(event, "extraction_backend") and event.extraction_backend:
                be = f" [{event.extraction_backend}]"
            ocr = " (OCR-Retry)" if getattr(event, "ocr_retry", False) else ""
            bf = ""
            if hasattr(event, "chunks_before_filter") and event.chunks_before_filter:
                bf = f" (vor Filter: {event.chunks_before_filter})"
            print(
                f"  [{event.doc_index}/{event.doc_total}] {event.datei}: "
                f"{event.chunks_total} Chunks{bf}{be}{ocr}"
            )
        elif event.phase == "enrich":
            print(f"  Kontextanreicherung...")

    payloads, stats = run_ingest(on_progress=_progress)
    t_ingest = time.monotonic() - t0

    print()
    print(f"  Extraktion abgeschlossen in {t_ingest:.1f}s")
    print(f"  docs_total={stats.docs_total}  success={stats.docs_success}  "
          f"skipped={stats.docs_skipped}  failed={stats.docs_failed}  "
          f"filtered_empty={stats.docs_filtered_empty}")
    print(f"  chunks_total={stats.chunks_total}")
    if stats.errors:
        print(f"  FEHLER:")
        for err in stats.errors:
            print(f"    - {err}")
    print()

    if not payloads:
        print("KEINE PAYLOADS — Abbruch.")
        return

    # Tabelle: Dokument → Chunk-Count
    print("--- Dokument → Chunk-Count ---")
    from collections import Counter
    doc_chunks: Counter[str] = Counter()
    for p in payloads:
        doc_chunks[p.datei] += 1
    for datei, count in sorted(doc_chunks.items()):
        print(f"  {datei:<60s} {count:>4d} Chunks")
    print(f"  {'GESAMT':<60s} {len(payloads):>4d} Chunks")
    print()

    # Schritt 3: Embed + Upsert
    print("--- Schritt 3: Embed + Upsert ---")
    t1 = time.monotonic()

    async def _embed():
        def _ep(event):
            print(f"  {event.detail}")
        return await embed_and_upsert(payloads, on_progress=_ep)

    result: IndexResult = asyncio.run(_embed())
    t_embed = time.monotonic() - t1
    print(f"  Embedding + Upsert in {t_embed:.1f}s")
    print(f"  embedded={result.chunks_embedded}  upserted={result.chunks_upserted}  "
          f"stale_deleted={result.chunks_stale_deleted}")
    print()

    # Schritt 4: Verifizierung
    print("--- Schritt 4: Verifizierung ---")
    info = client.get_collection(s.qdrant_collection)
    print(f"  Collection '{s.qdrant_collection}': {info.points_count} Punkte")
    print()
    print(f"=== FERTIG === Gesamt: {time.monotonic() - t0:.1f}s")


if __name__ == "__main__":
    main()
