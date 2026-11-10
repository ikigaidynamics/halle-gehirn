"""Diagnose-Script fuer q2 + q3 Eval-Failures.

Gibt fuer jede Frage aus:
- Vollstaendige Antwort
- Top-5 Sources mit datei + score
- Satz-fuer-Satz Grounding-Check (gestuetzt/geflaggt)
- Den Kontext-Text der dem Checker uebergeben wird
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT / "src"))

from halle_gehirn.config import get_settings
from halle_gehirn.pipeline.factory import build_query_pipeline
from halle_gehirn.pipeline.orchestrator import QueryOrchestrator
from halle_gehirn.pipeline.stages.grounding import (
    _extract_sentences,
    _format_context,
)

QUESTIONS = [
    {
        "id": "q2_mrk_demonstratoren",
        "query": "Welche Demonstratoren gibt es zur Mensch-Roboter-Kollaboration?",
    },
    {
        "id": "q3_predictive_maintenance",
        "query": "Welche Anbieter von Predictive-Maintenance-Loesungen gibt es?",
    },
]


async def diagnose_one(orch: QueryOrchestrator, q: dict, settings) -> None:
    print(f"\n{'=' * 80}")
    print(f"DIAGNOSE: {q['id']}")
    print(f"Query:    {q['query']}")
    print(f"{'=' * 80}")

    result = await orch.run(q["query"], debug=True)

    # 1. Vollstaendige Antwort
    print(f"\n--- VOLLSTAENDIGE ANTWORT (Ampel: {result.confidence}) ---")
    print(result.answer)

    # 2. Top-5 Sources
    print(f"\n--- TOP-5 SOURCES ---")
    for s in result.sources[:5]:
        print(f"  [{s['id']}] score={s['score']:.4f}  datei={s['datei']}")
        snippet = s.get("snippet", "")[:120]
        print(f"       snippet: {snippet}...")

    # 3. Grounding-Details
    if result.grounding:
        g = result.grounding
        print(f"\n--- GROUNDING ---")
        print(f"Score: {g.score:.3f}  ({g.grounded_sentences}/{g.total_sentences} gestuetzt)")
        print(f"Grounded: {g.grounded}  Threshold: {settings.grounding_threshold}")

        # Saetze extrahieren und gegen geflaggte abgleichen
        sentences = _extract_sentences(result.answer)
        print(f"\n--- SATZ-FUER-SATZ ANALYSE ({len(sentences)} Saetze) ---")
        for i, sent in enumerate(sentences, 1):
            is_flagged = sent in g.flagged_sentences
            status = "\033[91mGEFLAGGT\033[0m" if is_flagged else "\033[92mGESTUETZT\033[0m"
            print(f"\n  Satz {i}: {status}")
            print(f"    {sent}")

        if g.flagged_sentences:
            # Zeige auch den Kontext-Text (gekuerzt), den der Checker sieht
            # Wir brauchen die Hits - die stecken nicht im Result,
            # aber wir koennen die Top-5 datei-Felder zeigen
            print(f"\n--- GEFLAGGTE SAETZE (Detail) ---")
            for i, fs in enumerate(g.flagged_sentences, 1):
                print(f"  [{i}] {fs}")
    else:
        print(f"\n--- KEIN GROUNDING (rot = kein Check) ---")

    print()


async def main() -> None:
    settings = get_settings()
    print(f"Ollama: {settings.ollama_url}  |  LLM: {settings.llm_model}")
    print(f"Grounding-Threshold: {settings.grounding_threshold}")

    pipeline = build_query_pipeline(settings)
    orch = QueryOrchestrator(pipeline)

    for q in QUESTIONS:
        await diagnose_one(orch, q, settings)

    print("FERTIG.")


if __name__ == "__main__":
    asyncio.run(main())
