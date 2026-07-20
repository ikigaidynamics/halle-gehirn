"""Chunk-Qualitaets-Audit fuer die Qdrant-Collection.

Scrollt die gesamte ``halle_wissen``-Collection und analysiert die Chunks
in vier Phasen:

0. Inventar — Dokumente + Chunks zaehlen, Token-Statistik
1. Deterministische Flags — Red-Flag-Regeln (too_short, too_long, empty, …)
2. LLM-Judge — optional (``--skip-llm``), bewertet Chunks per Ollama
3. Synthese — Drop-Kandidaten-Liste (keine automatische Loeschung)

Aufruf::

    python -m scripts.analyze_chunks [--skip-llm] [--sample-pct 0.1] [--output report.json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

import structlog

from halle_gehirn.eval.chunk_audit import (
    AuditReport,
    ChunkFlag,
    DocSummary,
    LLMVerdict,
    build_doc_summary,
    flag_chunks,
    judge_chunks,
    synthesize,
)
from halle_gehirn.observability.logging_config import configure_logging
from halle_gehirn.pipeline.chunker import count_tokens
from halle_gehirn.vector_store.qdrant_client import (
    get_chunks_by_datei,
    list_indexed_documents,
)

logger = structlog.get_logger(__name__)


# ────────────────────────── Report-Formatierung ──────────────────────────


def _print_inventory(summaries: list[DocSummary]) -> None:
    """Druckt die Inventar-Tabelle."""
    print(f"\n{'='*72}")
    print("PHASE 0 — INVENTAR")
    print(f"{'='*72}")
    total_chunks = sum(s.chunk_count for s in summaries)
    print(f"  Dokumente: {len(summaries)}  |  Chunks gesamt: {total_chunks}\n")
    header = f"  {'Datei':<40} {'Chunks':>6} {'Body':>5} {'Tab':>4} {'Tok-Avg':>8} {'Min':>5} {'Max':>5}"
    print(header)
    print(f"  {'-'*69}")
    for s in summaries:
        name = s.datei if len(s.datei) <= 38 else "…" + s.datei[-37:]
        print(
            f"  {name:<40} {s.chunk_count:>6} {s.body_chunks:>5} "
            f"{s.table_chunks:>4} {s.token_mean:>8.1f} {s.token_min:>5} "
            f"{s.token_max:>5}"
        )


def _print_flags(flags: list[ChunkFlag]) -> None:
    """Druckt die deterministischen Flags gruppiert nach Regel."""
    print(f"\n{'='*72}")
    print("PHASE 1 — DETERMINISTISCHE FLAGS")
    print(f"{'='*72}")
    if not flags:
        print("  Keine Flags gefunden.")
        return

    by_rule = Counter(f.rule for f in flags)
    print(f"  Flags gesamt: {len(flags)}\n")
    for rule, count in by_rule.most_common():
        print(f"  {rule:<20} {count:>4}")

    print(f"\n  {'Regel':<16} {'Datei':<30} {'Idx':>4}  Detail")
    print(f"  {'-'*72}")
    for f in sorted(flags, key=lambda x: (x.datei, x.chunk_index)):
        datei_short = f.datei if len(f.datei) <= 28 else "…" + f.datei[-27:]
        print(f"  {f.rule:<16} {datei_short:<30} {f.chunk_index:>4}  {f.detail}")


def _print_verdicts(verdicts: list[LLMVerdict]) -> None:
    """Druckt die LLM-Judge-Verdicts."""
    print(f"\n{'='*72}")
    print("PHASE 2 — LLM-JUDGE-VERDICTS")
    print(f"{'='*72}")
    if not verdicts:
        print("  Keine Verdicts (LLM uebersprungen oder leer).")
        return

    by_verdict = Counter(v.verdict for v in verdicts)
    print(f"  Verdicts gesamt: {len(verdicts)}")
    for verdict, count in by_verdict.most_common():
        print(f"    {verdict:<12} {count:>4}")

    scores = [v.score for v in verdicts]
    print(f"\n  Score: min={min(scores):.2f}  mean={sum(scores)/len(scores):.2f}  max={max(scores):.2f}")

    # Details fuer drops und uncertain
    critical = [v for v in verdicts if v.verdict in ("drop", "uncertain")]
    if critical:
        print(f"\n  {'Verdict':<12} {'Score':>5} {'Datei':<28} {'Idx':>4}  Grund")
        print(f"  {'-'*72}")
        for v in sorted(critical, key=lambda x: x.score):
            datei_short = v.datei if len(v.datei) <= 26 else "…" + v.datei[-25:]
            reason_short = v.reason[:40] if len(v.reason) > 40 else v.reason
            print(f"  {v.verdict:<12} {v.score:>5.2f} {datei_short:<28} {v.chunk_index:>4}  {reason_short}")


def _print_drop_candidates(report: AuditReport) -> None:
    """Druckt die Drop-Kandidaten-Liste."""
    print(f"\n{'='*72}")
    print("PHASE 3 — DROP-KANDIDATEN")
    print(f"{'='*72}")
    if not report.drop_candidates:
        print("  Keine Drop-Kandidaten. Alle Chunks bestanden die Pruefung.")
        return

    print(f"  Drop-Kandidaten: {len(report.drop_candidates)}\n")
    print(f"  {'Point-ID':<34} {'Datei':<24} {'Idx':>4}  Grund")
    print(f"  {'-'*72}")
    for dc in report.drop_candidates:
        datei_short = dc["datei"]
        if len(datei_short) > 22:
            datei_short = "…" + datei_short[-21:]
        reason_short = dc["reason"][:30] if len(dc["reason"]) > 30 else dc["reason"]
        print(
            f"  {dc['point_id']:<34} {datei_short:<24} "
            f"{dc['chunk_index']:>4}  {reason_short}"
        )

    print(f"\n  HINWEIS: Keine automatische Loeschung. "
          f"Bitte manuell pruefen und ggf. ueber die UI entfernen.")


# ────────────────────────── Hauptlogik ──────────────────────────


def _run_audit(
    *, skip_llm: bool, sample_pct: float, output: Path | None,
) -> int:
    """Fuehrt das komplette Audit durch.

    Returns:
        Exit-Code (0 = OK, 1 = Drop-Kandidaten gefunden).
    """
    # Phase 0: Inventar
    print("Lade indexierte Dokumente aus Qdrant …")
    docs = list_indexed_documents()
    if not docs:
        print("  Keine Dokumente in der Collection gefunden.")
        return 0

    all_doc_chunks: dict[str, list[dict]] = {}
    summaries: list[DocSummary] = []

    for doc in docs:
        datei = doc["datei"]
        titel = doc.get("titel", "?")
        chunks = get_chunks_by_datei(datei)
        all_doc_chunks[datei] = chunks
        summaries.append(build_doc_summary(datei, titel, chunks))

    _print_inventory(summaries)

    # Phase 1: Deterministische Flags
    all_flags: list[ChunkFlag] = []
    for datei, chunks in all_doc_chunks.items():
        all_flags.extend(flag_chunks(chunks, datei))

    _print_flags(all_flags)

    # Phase 2: LLM-Judge
    all_verdicts: list[LLMVerdict] = []
    if skip_llm:
        print(f"\n{'='*72}")
        print("PHASE 2 — LLM-JUDGE (uebersprungen: --skip-llm)")
        print(f"{'='*72}")
    else:
        for datei, chunks in all_doc_chunks.items():
            flagged_ids = {f.point_id for f in all_flags if f.datei == datei}
            verdicts = asyncio.run(
                judge_chunks(
                    chunks, flagged_ids, datei, sample_pct=sample_pct,
                ),
            )
            all_verdicts.extend(verdicts)
        _print_verdicts(all_verdicts)

    # Phase 3: Synthese
    report = synthesize(summaries, all_flags, all_verdicts)
    _print_drop_candidates(report)

    # Optional: JSON-Export
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n  Report gespeichert: {output}")

    return 1 if report.drop_candidates else 0


def main() -> int:
    """CLI-Einstiegspunkt."""
    parser = argparse.ArgumentParser(
        description="Chunk-Qualitaets-Audit fuer die Qdrant-Collection",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="LLM-Judge uebersprungen (nur deterministische Flags)",
    )
    parser.add_argument(
        "--sample-pct",
        type=float,
        default=0.1,
        help="Anteil nicht-geflaggter Chunks als LLM-Sample (Default: 0.1)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Ausgabe als JSON-Datei (z.B. data/eval/chunk_audit.json)",
    )
    args = parser.parse_args()

    configure_logging(dev=True)
    return _run_audit(
        skip_llm=args.skip_llm,
        sample_pct=args.sample_pct,
        output=args.output,
    )


if __name__ == "__main__":
    raise SystemExit(main())
