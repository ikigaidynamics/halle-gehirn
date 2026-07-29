"""Eval-Runner -- Golden-Q&A-Baseline.

Laedt Fragen aus golden_qa.yaml, fuehrt sie ueber die Pipeline
(QueryOrchestrator), prueft 5 Signale (Ampel, Keywords, Forbidden,
Source, Grounding) und gibt eine Ergebnis-Tabelle + Gesamtquote aus.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml

from halle_gehirn.pipeline.orchestrator import QueryOrchestrator

_DEFAULT_QA_PATH = Path(__file__).resolve().parents[3] / "data" / "eval" / "golden_qa.yaml"


def load_golden_qa(path: Path | None = None) -> list[dict[str, Any]]:
    """Laedt Golden-Q&A-Fragen aus YAML."""
    p = path or _DEFAULT_QA_PATH
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["questions"]


async def run_eval(
    questions: list[dict[str, Any]],
    orchestrator: QueryOrchestrator,
    grounding_threshold: float = 0.5,
) -> list[dict[str, Any]]:
    """Fuehrt alle Fragen aus und prueft 5 Signale.

    Returns:
        Liste von Ergebnis-Dicts (eines je Frage).
    """
    results: list[dict[str, Any]] = []

    for q in questions:
        qid = q["id"]
        query = q["query"]
        expected_keywords: list[str] = q.get("expected_keywords", [])
        forbidden_keywords: list[str] = q.get("forbidden_keywords", [])
        expected_confidence: str = q["expected_confidence"]
        expected_src_raw = q.get("expected_source_contains")
        # Normalisieren: String oder Liste → immer Liste
        if expected_src_raw is None:
            expected_srcs: list[str] = []
        elif isinstance(expected_src_raw, str):
            expected_srcs = [expected_src_raw]
        else:
            expected_srcs = list(expected_src_raw)

        start = time.monotonic()
        result = await orchestrator.run(query, debug=True)
        latency_ms = (time.monotonic() - start) * 1000

        answer_lower = result.answer.lower()
        grounding_score = result.grounding.score if result.grounding else None

        # 1. Ampel-Pruefung
        confidence_ok = result.confidence == expected_confidence

        # 2. Stichwort-Pruefung (case-insensitive)
        keywords_found = [kw for kw in expected_keywords if kw.lower() in answer_lower]
        keywords_missing = [kw for kw in expected_keywords if kw.lower() not in answer_lower]
        keywords_ok = len(keywords_missing) == 0

        # 3. Forbidden-Keywords (Refusal-Pruefung)
        forbidden_found = [kw for kw in forbidden_keywords if kw.lower() in answer_lower]
        forbidden_ok = len(forbidden_found) == 0

        # 4. Source-Pruefung (richtiges Dokument? OR-Logik bei Liste)
        top_source = result.sources[0].get("datei", "") if result.sources else ""
        if expected_srcs:
            source_ok = any(
                s.lower() in top_source.lower() for s in expected_srcs
            )
        else:
            source_ok = True

        # 5. Grounding-Gate (nur fuer gruene Fragen)
        grounding_ok = True
        if expected_confidence == "gruen" and grounding_score is not None:
            grounding_ok = grounding_score >= grounding_threshold

        # PASSED: alle Signale muessen zusammenpassen
        passed = confidence_ok and keywords_ok and forbidden_ok and source_ok and grounding_ok

        results.append({
            "id": qid,
            "query": query,
            "answer_snippet": result.answer[:200],
            "confidence": result.confidence,
            "expected_confidence": expected_confidence,
            "confidence_ok": confidence_ok,
            "keywords_found": keywords_found,
            "keywords_missing": keywords_missing,
            "keywords_ok": keywords_ok,
            "forbidden_found": forbidden_found,
            "forbidden_ok": forbidden_ok,
            "top_source": top_source,
            "source_ok": source_ok,
            "grounding_score": round(grounding_score, 3) if grounding_score is not None else None,
            "grounding_ok": grounding_ok,
            "latency_ms": round(latency_ms),
            "sources_count": len(result.sources),
            "passed": passed,
        })

    return results


def print_report(results: list[dict[str, Any]]) -> None:
    """Gibt die Ergebnis-Tabelle + Gesamtquote aus."""
    print()
    print(f"{'ID':<24s} {'Ampel':<6s} {'Erw.':<6s} {'KW':<6s} "
          f"{'Forb':<5s} {'Source':<7s} {'Ground':<7s} {'Latenz':<9s} {'PASS'}")
    print("-" * 85)

    for r in results:
        qid = r["id"]
        if len(qid) > 23:
            qid = qid[:20] + "..."

        kw_total = len(r["keywords_found"]) + len(r["keywords_missing"])
        kw_str = f"{len(r['keywords_found'])}/{kw_total}" if kw_total > 0 else "-/-"

        forb_str = "ok" if r["forbidden_ok"] else f"FAIL({len(r['forbidden_found'])})"

        src_str = "ok" if r["source_ok"] else "FAIL"
        if r["expected_confidence"] == "rot":
            src_str = "-"

        gs = r["grounding_score"]
        ground_str = f"{gs:.2f}" if gs is not None else "-"

        latency_str = f"{r['latency_ms']}ms"

        pass_str = "\033[92mOK\033[0m" if r["passed"] else "\033[91mFAIL\033[0m"

        print(f"{qid:<24s} {r['confidence']:<6s} {r['expected_confidence']:<6s} "
              f"{kw_str:<6s} {forb_str:<5s} {src_str:<7s} {ground_str:<7s} "
              f"{latency_str:<9s} {pass_str}")

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    pct = (passed / total * 100) if total > 0 else 0
    print("-" * 85)
    color = "\033[92m" if passed == total else "\033[93m"
    print(f"\nGesamt: {color}{passed}/{total} bestanden ({pct:.0f}%)\033[0m")
    print()
