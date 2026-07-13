"""Chunk-Qualitaets-Report fuer die Indexierungs-Schicht.

Laesst den repraesentativen Abschlussarbeit-Korpus (siehe
``tests/test_chunk_quality.py``) durch Chunker + Filter laufen und druckt
einen lesbaren Qualitaets-Report: Token-Verteilung, Fragmentierung,
Heading-Abdeckung, Tabellen-Integritaet und Zeichen-Abdeckung.

Aufruf::

    python scripts/eval_chunk_quality.py

Netzfrei ausser der einmaligen tiktoken-Encoding-Aufloesung (gecacht).
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from halle_gehirn.config import get_settings  # noqa: E402
from halle_gehirn.eval.chunk_quality import (  # noqa: E402
    ChunkQualityReport,
    QualityThresholds,
    evaluate_chunks,
)
from halle_gehirn.pipeline.chunk_filter import filter_chunks  # noqa: E402
from halle_gehirn.pipeline.chunker import (  # noqa: E402
    Chunk,
    MarkdownChunker,
    count_tokens,
)
from tests.test_chunk_quality import build_abschlussarbeit  # noqa: E402


def _histogram(chunks: list[Chunk]) -> str:
    """Baut ein einfaches ASCII-Histogramm der Token-Verteilung."""
    buckets = [0, 64, 128, 256, 384, 512, 640, 768]
    labels = [
        "  0- 64", " 64-128", "128-256", "256-384",
        "384-512", "512-640", "640-768", "  >768",
    ]
    counts = [0] * len(labels)
    for chunk in chunks:
        tk = count_tokens(chunk.text)
        placed = False
        for i in range(len(buckets) - 1):
            if buckets[i] <= tk < buckets[i + 1]:
                counts[i] += 1
                placed = True
                break
        if not placed:
            counts[-1] += 1
    lines = ["  Token-Verteilung (alle Chunks):"]
    for label, count in zip(labels, counts, strict=True):
        bar = "█" * count
        lines.append(f"    {label} | {bar} {count}")
    return "\n".join(lines)


def _print_report(title: str, report: ChunkQualityReport) -> None:
    """Druckt einen ChunkQualityReport lesbar."""
    d = report.as_dict()
    print(f"\n── {title} ──")
    print(f"  Chunks gesamt : {d['total_chunks']} "
          f"(Body {d['body_chunks']}, Tabelle {d['table_chunks']})")
    print(f"  Tokens        : min {d['token_min']} · median "
          f"{d['token_median']} · mean {d['token_mean']} · p90 "
          f"{d['token_p90']} · max {d['token_max']}")
    print(f"  Ueber max     : {d['oversize_count']}  (Ziel 0)")
    print(f"  Fragmente     : {d['fragment_count']}  (Body < 64 Tokens)")
    print(f"  Gesundes Band : {d['healthy_fraction'] * 100:.0f} %  "
          f"(Body im Band [64, max])")
    print(f"  Heading-Cov.  : {d['heading_coverage'] * 100:.0f} %  "
          f"(Body-Chunks mit Heading)")
    print(f"  Tabellen-Head : {d['table_header_fraction'] * 100:.0f} %  "
          f"(Teile mit Header)")
    print(f"  Zeichen-Abd.  : {d['char_coverage'] * 100:.0f} %  "
          f"(Body-Zeichen abgedeckt)")
    print(f"  Seiten-Abd.   : {d['page_coverage'] * 100:.0f} %  "
          f"(Chunks mit Seite — 0 % ohne Page-Map)")
    print(f"  Leere Chunks  : {d['empty_chunks']}  (Ziel 0)")


def main() -> int:
    """Erzeugt und druckt den Chunk-Qualitaets-Report. 0 = alles gruen."""
    s = get_settings()
    thresholds = QualityThresholds(
        max_tokens=s.chunk_max_tokens,
        target_tokens=s.chunk_target_tokens,
    )
    doc = build_abschlussarbeit()
    chunker = MarkdownChunker()
    raw = chunker.chunk(doc, doc_type="abschlussarbeit")
    kept = filter_chunks(raw, doc_type="abschlussarbeit")

    print("=" * 60)
    print("CHUNK-QUALITAETS-REPORT — Korpus: Abschlussarbeit (Demo)")
    print("=" * 60)
    print(f"  Body-Zeichen: {len(doc.body_md)} · "
          f"Body-Tokens: {count_tokens(doc.body_md)} · "
          f"Tabellen: {len(doc.tables)}")
    print(f"  Config: target={s.chunk_target_tokens} "
          f"max={s.chunk_max_tokens} min_chars={s.min_chunk_chars}")

    raw_report = evaluate_chunks(raw, doc.body_md, thresholds)
    kept_report = evaluate_chunks(kept, doc.body_md, thresholds)
    _print_report("VOR Filter (Chunker-Fidelitaet)", raw_report)
    _print_report("NACH Filter (Index-Kandidaten)", kept_report)
    print()
    print(_histogram(kept))

    # Exit-Code: harte Garantien
    ok = (
        kept_report.oversize_count == 0
        and kept_report.empty_chunks == 0
        and kept_report.table_header_fraction == 1.0
    )
    print("\n" + ("✅ Harte Garantien erfuellt." if ok
                  else "❌ Harte Garantien VERLETZT."))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
