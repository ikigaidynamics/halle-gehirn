"""Chunk-Qualitaets-Metrik fuer die Indexierungs-Schicht.

Bewertet die Ausgabe des ``MarkdownChunker`` (+ optional ``filter_chunks``)
objektiv: Token-Verteilung, Fragmentierung, Heading-Abdeckung, Tabellen-
Integritaet und Zeichen-Abdeckung des Quelltexts. Reiner, netzfreier Code —
nutzbar aus Tests (Invarianten) und aus dem Report-Skript (Kennzahlen).

Keine Halluzinations-relevante Aussage ohne Beleg: die Metrik misst nur, was
aus den ``Chunk``-Objekten und dem Body-Markdown ableitbar ist.
"""
from __future__ import annotations

from dataclasses import dataclass

from halle_gehirn.pipeline.chunker import Chunk, count_tokens

# Separator-Zeile einer Markdown-Tabelle (Header-Beleg je Teil)
_TABLE_SEP = "---"


@dataclass(frozen=True)
class QualityThresholds:
    """Schwellen fuer die Qualitaetsbewertung (aus Config ableitbar)."""

    max_tokens: int = 768
    target_tokens: int = 512
    min_healthy_tokens: int = 64  # darunter gilt ein Body-Chunk als Fragment


@dataclass(frozen=True)
class ChunkQualityReport:
    """Aggregierte Qualitaetskennzahlen eines Chunk-Satzes."""

    total_chunks: int
    body_chunks: int
    table_chunks: int
    token_min: int
    token_mean: float
    token_median: float
    token_p90: int
    token_max: int
    oversize_count: int  # Chunks ueber max_tokens (muss 0 sein)
    fragment_count: int  # Body-Chunks unter min_healthy_tokens
    healthy_fraction: float  # Body-Chunks im Band [min_healthy, max]
    heading_coverage: float  # Body-Chunks mit >=1 Heading
    table_header_fraction: float  # Tabellen-Chunks mit Separator-Zeile
    char_coverage: float  # Anteil Body-Zeichen, den Body-Chunks abdecken
    page_coverage: float  # Anteil Chunks mit gesetzter Seite (Zitate)
    empty_chunks: int  # Chunks ohne sichtbaren Text (muss 0 sein)

    def as_dict(self) -> dict[str, float | int]:
        """Flache Dict-Repraesentation (fuer Logging/JSON)."""
        return {
            "total_chunks": self.total_chunks,
            "body_chunks": self.body_chunks,
            "table_chunks": self.table_chunks,
            "token_min": self.token_min,
            "token_mean": round(self.token_mean, 1),
            "token_median": round(self.token_median, 1),
            "token_p90": self.token_p90,
            "token_max": self.token_max,
            "oversize_count": self.oversize_count,
            "fragment_count": self.fragment_count,
            "healthy_fraction": round(self.healthy_fraction, 3),
            "heading_coverage": round(self.heading_coverage, 3),
            "table_header_fraction": round(self.table_header_fraction, 3),
            "char_coverage": round(self.char_coverage, 3),
            "page_coverage": round(self.page_coverage, 3),
            "empty_chunks": self.empty_chunks,
        }


def _percentile(sorted_vals: list[int], pct: float) -> int:
    """Naechster-Rang-Perzentil auf sortierter Liste (leer → 0)."""
    if not sorted_vals:
        return 0
    idx = min(len(sorted_vals) - 1, round(pct * (len(sorted_vals) - 1)))
    return sorted_vals[idx]


def _median(sorted_vals: list[int]) -> float:
    """Median einer sortierten Liste (leer → 0.0)."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2:
        return float(sorted_vals[mid])
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2


def _char_coverage(body_chunks: list[Chunk], body: str) -> float:
    """Anteil der Body-Zeichen, den die Body-Chunk-Spannen abdecken.

    Vereinigt die ``[char_start, char_end)``-Intervalle der Body-Chunks
    und teilt durch die Body-Laenge. Tabellen-Chunks haben keine Body-
    Offsets und bleiben aussen vor.
    """
    if not body:
        return 0.0
    n = len(body)
    spans = sorted(
        (max(0, c.char_start), min(n, c.char_end))
        for c in body_chunks
        if c.char_end > c.char_start
    )
    covered = 0
    cursor = 0
    for start, end in spans:
        if end <= cursor:
            continue
        covered += end - max(start, cursor)
        cursor = end
    return covered / n


def evaluate_chunks(
    chunks: list[Chunk],
    source_body: str | None = None,
    thresholds: QualityThresholds | None = None,
) -> ChunkQualityReport:
    """Berechnet Qualitaetskennzahlen fuer einen Chunk-Satz.

    Args:
        chunks: Ausgabe des Chunkers (optional bereits gefiltert).
        source_body: Body-Markdown fuer die Zeichen-Abdeckung (optional).
        thresholds: Schwellen; Default ``QualityThresholds()``.

    Returns:
        Aggregierter ``ChunkQualityReport``.
    """
    t = thresholds or QualityThresholds()
    body = [c for c in chunks if not c.is_table]
    tables = [c for c in chunks if c.is_table]
    tokens = [count_tokens(c.text) for c in chunks]
    tokens_sorted = sorted(tokens)

    body_tokens = [count_tokens(c.text) for c in body]
    healthy = sum(
        1 for tk in body_tokens if t.min_healthy_tokens <= tk <= t.max_tokens
    )
    fragments = sum(1 for tk in body_tokens if tk < t.min_healthy_tokens)
    with_heading = sum(1 for c in body if c.headings)
    tables_with_header = sum(1 for c in tables if _TABLE_SEP in c.text)
    empty = sum(1 for c in chunks if not c.text.strip())

    return ChunkQualityReport(
        total_chunks=len(chunks),
        body_chunks=len(body),
        table_chunks=len(tables),
        token_min=tokens_sorted[0] if tokens_sorted else 0,
        token_mean=(sum(tokens) / len(tokens)) if tokens else 0.0,
        token_median=_median(tokens_sorted),
        token_p90=_percentile(tokens_sorted, 0.9),
        token_max=tokens_sorted[-1] if tokens_sorted else 0,
        oversize_count=sum(1 for tk in tokens if tk > t.max_tokens),
        fragment_count=fragments,
        healthy_fraction=(healthy / len(body)) if body else 1.0,
        heading_coverage=(with_heading / len(body)) if body else 1.0,
        table_header_fraction=(
            tables_with_header / len(tables) if tables else 1.0
        ),
        char_coverage=(
            _char_coverage(body, source_body)
            if source_body is not None
            else 0.0
        ),
        page_coverage=(
            sum(1 for c in chunks if c.page is not None) / len(chunks)
            if chunks else 0.0
        ),
        empty_chunks=empty,
    )
