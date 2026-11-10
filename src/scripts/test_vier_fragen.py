"""Vier Testfragen mit Rewriter-Turns und JSONL-Logs.

Fuehrt 4 Fragen durch die komplette Pipeline (incl. Query-Rewriter)
und gibt Wortlaut, Quellen, Ampel, Latenz aus. Die JSONL-Logs werden
automatisch vom Pipeline-Logger geschrieben (logs/retrieval/YYYY-MM-DD.jsonl).

Frage 4 ist ein Follow-up auf Frage 3 — testet den Query-Rewriter.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Projekt-Root in sys.path
_PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT / "src"))

from halle_gehirn.config import get_settings
from halle_gehirn.pipeline.factory import build_query_pipeline
from halle_gehirn.pipeline.orchestrator import QueryOrchestrator, QueryResult

# Session-ID: Fragen 3+4 teilen eine Session (Rewriter-Test)
_SESSION_A = "test-allgemein"
_SESSION_B = "test-followup"

# Die vier Fragen
FRAGEN: list[tuple[str, str]] = [
    (
        "Welche Demonstratoren gibt es in der Modellfabrik und wofuer werden sie eingesetzt?",
        _SESSION_A,
    ),
    (
        "Welche Rolle spielt Predictive Maintenance in den Forschungsarbeiten des Lehrstuhls?",
        _SESSION_A,
    ),
    (
        "Was beschreibt die Masterarbeit von Ronny Porsch zum Thema Industrial Metaverse?",
        _SESSION_B,
    ),
    # Follow-up: "dabei" + kurze Frage → Rewriter sollte aufloesen
    (
        "Welche Technologien wurden dabei eingesetzt?",
        _SESSION_B,
    ),
]

_AMPEL = {"gruen": "\033[92mGRUEN\033[0m", "gelb": "\033[93mGELB\033[0m", "rot": "\033[91mROT\033[0m"}


def _print_result(idx: int, frage: str, result: QueryResult) -> None:
    ampel = _AMPEL.get(result.confidence, result.confidence)
    rewritten = result.debug_info.get("query_rewritten", "")
    was_rewritten = result.debug_info.get("was_rewritten", False)

    print(f"\n{'=' * 72}")
    print(f"FRAGE {idx}: {frage}")
    print(f"{'=' * 72}")

    if was_rewritten:
        print(f"  Rewritten:  {rewritten}")
    else:
        print(f"  Rewritten:  (nicht umgeschrieben)")

    print(f"  Ampel:      {ampel}")
    print(f"  Latenz:     {result.latency_ms:.0f} ms")
    print(f"  Query-Type: {result.debug_info.get('query_type', '-')}")
    print(f"  Hits:       {result.debug_info.get('retrieval_hits', '-')}")
    print()

    # Quellen
    print(f"  Quellen ({len(result.sources)}):")
    for s in result.sources[:5]:
        score = s.get("score", 0)
        datei = s.get("datei", "")
        page = s.get("page")
        page_str = f" S.{page}" if page else ""
        print(f"    [{s['id']}] {datei}{page_str}  (score={score:.4f})")
    print()

    # Antwort (gekuerzt)
    answer = result.answer.strip()
    if len(answer) > 500:
        answer = answer[:500] + " [...]"
    print(f"  Antwort:\n    {answer}")


async def main() -> None:
    s = get_settings()
    print(f"=== Vier Testfragen ===")
    print(f"Ollama: {s.ollama_url}  |  LLM: {s.llm_model}")
    print(f"Embedding: {s.embedding_model}  |  Qdrant: {s.qdrant_url}")
    print(f"Query-Rewrite: {'AN' if s.use_query_rewrite else 'AUS'}")
    print(f"Retrieval-Log: {'AN' if s.retrieval_log_enabled else 'AUS'} ({s.retrieval_log_dir})")

    pipeline = build_query_pipeline(s)
    orch = QueryOrchestrator(pipeline)

    for idx, (frage, session_id) in enumerate(FRAGEN, start=1):
        result = await orch.run(frage, session_id=session_id, debug=True)
        _print_result(idx, frage, result)

    # JSONL-Log Hinweis
    from datetime import date
    log_path = Path(s.retrieval_log_dir) / f"{date.today().isoformat()}.jsonl"
    print(f"\n{'=' * 72}")
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        print(f"JSONL-Log: {log_path} ({len(lines)} Eintraege)")
    else:
        print(f"JSONL-Log: {log_path} (noch nicht vorhanden)")
    print(f"{'=' * 72}")
    print("FERTIG.")


if __name__ == "__main__":
    asyncio.run(main())
