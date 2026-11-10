"""Zeigt wie viel vom Kontext der Grounding-Checker sieht (3000-Char-Limit)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT / "src"))

from halle_gehirn.config import get_settings
from halle_gehirn.pipeline.factory import build_query_pipeline
from halle_gehirn.pipeline.stages.grounding import _format_context

settings = get_settings()
pipeline = build_query_pipeline(settings)

async def main():
    # q2 simulieren: gleiche Query
    query = "Welche Demonstratoren gibt es zur Mensch-Roboter-Kollaboration?"
    from halle_gehirn.pipeline.orchestrator import QueryOrchestrator
    orch = QueryOrchestrator(pipeline)

    # Wir brauchen die rohen Hits - laufen die Retrieval-Stufen manuell
    queries = await pipeline.query_transformer.transform(query)
    hits = await orch._retrieve_dedup(queries, None)

    context_full = _format_context(hits)
    context_truncated = context_full[:3000]

    print(f"Kontext GESAMT: {len(context_full)} Zeichen")
    print(f"Kontext TRUNCATED (was Checker sieht): {len(context_truncated)} Zeichen")
    print(f"Abgeschnitten: {len(context_full) - 3000} Zeichen ({(len(context_full)-3000)/len(context_full)*100:.0f}%)")
    print()

    # Zeige wo der Cut faellt
    print("=== TRUNCATED KONTEXT ENDET BEI: ===")
    print(context_truncated[-200:])
    print()
    print("=== WAS DANACH KOMMT (erste 500 Zeichen): ===")
    rest = context_full[3000:3500]
    print(rest)
    print()

    # Welche Sources sind im truncated context?
    for i, hit in enumerate(hits, 1):
        payload = getattr(hit, "payload", {}) or {}
        datei = payload.get("datei", "")
        text = payload.get("text", "")
        # Check ob der Text im truncated context vorkommt
        teil = text[:50]
        in_trunc = teil in context_truncated if teil else False
        print(f"  S{i}: datei={datei}  text_len={len(text)}  im_truncated={in_trunc}")

asyncio.run(main())
