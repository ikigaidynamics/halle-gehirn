"""Eval-Baseline -- fuehrt Golden-Q&A gegen die Pipeline aus.

Braucht laufendes Qdrant + Ollama.
Aufruf:  .venv/Scripts/python.exe src/scripts/eval_baseline.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Projekt-Root in sys.path
_PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT / "src"))

from halle_gehirn.config import get_settings
from halle_gehirn.eval.runner import load_golden_qa, print_report, run_eval
from halle_gehirn.pipeline.factory import build_query_pipeline
from halle_gehirn.pipeline.orchestrator import QueryOrchestrator


async def main() -> None:
    settings = get_settings()
    print(f"=== Eval-Baseline ===")
    print(f"Ollama: {settings.ollama_url}  |  LLM: {settings.llm_model}")
    print(f"Qdrant: {settings.qdrant_url}  |  Grounding-Threshold: {settings.grounding_threshold}")

    pipeline = build_query_pipeline(settings)
    orch = QueryOrchestrator(pipeline)

    questions = load_golden_qa()
    print(f"Fragen: {len(questions)}")
    print()

    results = await run_eval(questions, orch, settings.grounding_threshold)
    print_report(results)


if __name__ == "__main__":
    asyncio.run(main())
