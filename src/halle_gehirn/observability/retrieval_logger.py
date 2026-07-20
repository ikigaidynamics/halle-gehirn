"""Retrieval-JSONL-Logger -- Per-Request Debugging.

Schreibt eine JSONL-Zeile pro Pipeline-Durchlauf mit Retrieval-Metadaten,
Latenz-Aufschluesselung und Chunk-Scores. KEIN Antworttext (nur Laengen).
Taegliche Rotation, append-only. Fail-silent bei I/O-Fehlern.

GETRENNT von audit.py (structlog) -- dieses Modul ist dateibasiert.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class LatencyBreakdown:
    """Latenz-Aufschluesselung pro Pipeline-Stage (in ms)."""

    rewrite_ms: float = 0.0
    embed_ms: float = 0.0
    search_ms: float = 0.0
    rerank_ms: float = 0.0
    generate_ms: float = 0.0
    total_ms: float = 0.0


@dataclass
class RetrievalLogEntry:
    """Ein JSONL-Eintrag pro Request."""

    timestamp: str
    session_id: str
    query_original: str
    query_rewritten: str
    was_rewritten: bool
    query_type: str
    chunks: list[dict[str, Any]]
    confidence: str
    outcome: str  # "answered" | "refusal" | "blocked" | "smalltalk"
    answer_length: int
    latency: LatencyBreakdown = field(default_factory=LatencyBreakdown)


class RetrievalJsonlLogger:
    """Append-only JSONL-Logger fuer Retrieval-Debugging.

    Schreibt eine Zeile pro Request in eine tagesaktuelle Datei.
    Thread-safe durch append-mode. Fail-silent bei I/O-Fehlern.

    Args:
        log_dir: Verzeichnis fuer JSONL-Dateien.
    """

    def __init__(self, log_dir: Path) -> None:
        self._log_dir = log_dir

    def log(self, entry: RetrievalLogEntry) -> None:
        """Schreibt den Eintrag als JSONL-Zeile.

        Fail-silent: bei I/O-Fehler wird nur gewarnt.
        """
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{date.today().isoformat()}.jsonl"
            path = self._log_dir / filename
            line = json.dumps(asdict(entry), ensure_ascii=False)
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as exc:
            logger.warning("retrieval_log_write_failed", error=str(exc))


class PipelineTimer:
    """Hilfsklasse zum Messen von Stage-Latenzen.

    Nutzung:
        timer = PipelineTimer()
        timer.start("embed")
        ...
        timer.stop("embed")
        breakdown = timer.breakdown()
    """

    def __init__(self) -> None:
        self._starts: dict[str, float] = {}
        self._durations: dict[str, float] = {}
        self._pipeline_start = time.monotonic()

    def start(self, stage: str) -> None:
        """Startet die Zeitmessung fuer eine Stage."""
        self._starts[stage] = time.monotonic()

    def stop(self, stage: str) -> None:
        """Stoppt die Zeitmessung fuer eine Stage."""
        if stage in self._starts:
            elapsed = (time.monotonic() - self._starts[stage]) * 1000
            self._durations[stage] = elapsed

    def get(self, stage: str) -> float:
        """Liefert die gemessene Dauer einer Stage in ms."""
        return self._durations.get(stage, 0.0)

    def breakdown(self) -> LatencyBreakdown:
        """Liefert die Latenz-Aufschluesselung."""
        total = (time.monotonic() - self._pipeline_start) * 1000
        return LatencyBreakdown(
            rewrite_ms=round(self._durations.get("rewrite", 0.0), 1),
            embed_ms=round(self._durations.get("embed", 0.0), 1),
            search_ms=round(self._durations.get("search", 0.0), 1),
            rerank_ms=round(self._durations.get("rerank", 0.0), 1),
            generate_ms=round(self._durations.get("generate", 0.0), 1),
            total_ms=round(total, 1),
        )


def build_log_entry(
    *,
    session_id: str,
    query_original: str,
    query_rewritten: str,
    was_rewritten: bool,
    query_type: str,
    hits: list[Any],
    confidence: str,
    outcome: str,
    answer_length: int,
    timer: PipelineTimer,
) -> RetrievalLogEntry:
    """Baut einen RetrievalLogEntry aus Pipeline-Daten.

    Args:
        hits: RetrievalHit-Objekte (top-k final).
        Restliche Argumente: Pipeline-Metadaten.

    Returns:
        Fertiger RetrievalLogEntry.
    """
    chunks: list[dict[str, Any]] = []
    for rank, hit in enumerate(hits[:10], start=1):
        payload = getattr(hit, "payload", {}) or {}
        chunks.append({
            "point_id": getattr(hit, "point_id", ""),
            "titel": payload.get("titel", ""),
            "datei": payload.get("datei", ""),
            "score": round(getattr(hit, "rerank_score", 0.0), 4),
            "rank": rank,
        })

    return RetrievalLogEntry(
        timestamp=datetime.now(UTC).isoformat(),
        session_id=session_id,
        query_original=query_original,
        query_rewritten=query_rewritten,
        was_rewritten=was_rewritten,
        query_type=query_type,
        chunks=chunks,
        confidence=confidence,
        outcome=outcome,
        answer_length=answer_length,
        latency=timer.breakdown(),
    )
