"""Tests fuer Retrieval-JSONL-Logger.

Prueft PipelineTimer, JSONL-Dateioperationen, Fail-Silent-Semantik
und korrekte Latenz-Aufschluesselung.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from halle_gehirn.observability.retrieval_logger import (
    LatencyBreakdown,
    PipelineTimer,
    RetrievalJsonlLogger,
    RetrievalLogEntry,
    build_log_entry,
)

# ═══════════════════ PipelineTimer ═══════════════════


class TestPipelineTimer:
    """Tests fuer den PipelineTimer."""

    def test_start_stop_records_duration(self) -> None:
        """Start/Stop misst eine Dauer > 0."""
        timer = PipelineTimer()
        timer.start("embed")
        time.sleep(0.01)
        timer.stop("embed")

        breakdown = timer.breakdown()
        assert breakdown.embed_ms > 0

    def test_breakdown_returns_all_stages(self) -> None:
        """Alle Stages sind im Breakdown enthalten."""
        timer = PipelineTimer()
        timer.start("rewrite")
        timer.stop("rewrite")
        timer.start("embed")
        timer.stop("embed")
        timer.start("search")
        timer.stop("search")
        timer.start("rerank")
        timer.stop("rerank")
        timer.start("generate")
        timer.stop("generate")

        breakdown = timer.breakdown()
        assert breakdown.rewrite_ms >= 0
        assert breakdown.embed_ms >= 0
        assert breakdown.search_ms >= 0
        assert breakdown.rerank_ms >= 0
        assert breakdown.generate_ms >= 0
        assert breakdown.total_ms >= 0

    def test_missing_stop_returns_zero(self) -> None:
        """Ohne stop(): Stage bleibt bei 0."""
        timer = PipelineTimer()
        timer.start("embed")
        # Kein stop()!
        breakdown = timer.breakdown()
        assert breakdown.embed_ms == 0.0

    def test_get_returns_duration(self) -> None:
        """get() liefert die gemessene Dauer."""
        timer = PipelineTimer()
        timer.start("search")
        time.sleep(0.01)
        timer.stop("search")

        assert timer.get("search") > 0
        assert timer.get("nonexistent") == 0.0

    def test_total_includes_full_pipeline_time(self) -> None:
        """total_ms misst die gesamte Pipeline-Dauer."""
        timer = PipelineTimer()
        time.sleep(0.02)
        breakdown = timer.breakdown()
        assert breakdown.total_ms >= 15  # mindestens ~20ms


# ═══════════════════ RetrievalJsonlLogger ═══════════════════


class TestRetrievalJsonlLogger:
    """Tests fuer den JSONL-Logger."""

    def test_creates_daily_file(self, tmp_path: Path) -> None:
        """Erstellt eine tagesaktuelle JSONL-Datei."""
        logger = RetrievalJsonlLogger(log_dir=tmp_path)
        entry = _make_entry()
        logger.log(entry)

        files = list(tmp_path.glob("*.jsonl"))
        assert len(files) == 1
        assert files[0].name.endswith(".jsonl")

    def test_appends_to_existing_file(self, tmp_path: Path) -> None:
        """Haengt an existierende Datei an."""
        logger = RetrievalJsonlLogger(log_dir=tmp_path)
        logger.log(_make_entry())
        logger.log(_make_entry())

        files = list(tmp_path.glob("*.jsonl"))
        lines = files[0].read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

    def test_valid_json_lines(self, tmp_path: Path) -> None:
        """Jede Zeile ist valides JSON."""
        logger = RetrievalJsonlLogger(log_dir=tmp_path)
        logger.log(_make_entry())

        files = list(tmp_path.glob("*.jsonl"))
        content = files[0].read_text(encoding="utf-8").strip()
        data = json.loads(content)
        assert data["session_id"] == "test-session"
        assert data["confidence"] == "gruen"
        assert "latency" in data

    def test_no_answer_text_in_output(self, tmp_path: Path) -> None:
        """Kein Antworttext im Log (nur Laenge)."""
        logger = RetrievalJsonlLogger(log_dir=tmp_path)
        logger.log(_make_entry())

        files = list(tmp_path.glob("*.jsonl"))
        content = files[0].read_text(encoding="utf-8")
        data = json.loads(content)
        assert "answer_length" in data
        assert "answer" not in data
        assert "answer_text" not in data

    def test_fail_silent_on_io_error(self) -> None:
        """Bei I/O-Fehler: kein Crash."""
        logger = RetrievalJsonlLogger(
            log_dir=Path("/nonexistent/path/that/wont/exist"),
        )
        # Sollte nicht werfen
        logger.log(_make_entry())

    def test_latency_breakdown_populated(self, tmp_path: Path) -> None:
        """embed_ms, search_ms, rerank_ms sind einzeln sichtbar."""
        logger = RetrievalJsonlLogger(log_dir=tmp_path)
        entry = _make_entry()
        entry.latency = LatencyBreakdown(
            rewrite_ms=5.0,
            embed_ms=120.0,
            search_ms=15.0,
            rerank_ms=800.0,
            generate_ms=3000.0,
            total_ms=4000.0,
        )
        logger.log(entry)

        files = list(tmp_path.glob("*.jsonl"))
        data = json.loads(files[0].read_text(encoding="utf-8"))
        latency = data["latency"]
        assert latency["embed_ms"] == 120.0
        assert latency["search_ms"] == 15.0
        assert latency["rerank_ms"] == 800.0
        assert latency["generate_ms"] == 3000.0


# ═══════════════════ build_log_entry ═══════════════════


class TestBuildLogEntry:
    """Tests fuer die build_log_entry Hilfsfunktion."""

    def test_builds_entry_from_hits(self) -> None:
        """Baut korrekten Eintrag aus RetrievalHits."""
        from tests.test_orchestrator import FakeHit

        hits = [
            FakeHit(point_id="a1", rerank_score=0.9),
            FakeHit(point_id="b2", rerank_score=0.7),
        ]
        timer = PipelineTimer()

        entry = build_log_entry(
            session_id="s1",
            query_original="Was kann der?",
            query_rewritten="Was kann der UR10e?",
            was_rewritten=True,
            query_type="factual",
            hits=hits,
            confidence="gruen",
            outcome="answered",
            answer_length=150,
            timer=timer,
        )

        assert entry.session_id == "s1"
        assert entry.was_rewritten is True
        assert len(entry.chunks) == 2
        assert entry.chunks[0]["rank"] == 1
        assert entry.chunks[0]["score"] == 0.9
        assert entry.outcome == "answered"


# ═══════════════════ Hilfsfunktionen ═══════════════════


def _make_entry() -> RetrievalLogEntry:
    """Erzeugt einen Test-Eintrag."""
    return RetrievalLogEntry(
        timestamp="2026-07-19T10:00:00+00:00",
        session_id="test-session",
        query_original="Was kann der?",
        query_rewritten="Was kann der UR10e Roboterarm?",
        was_rewritten=True,
        query_type="factual",
        chunks=[
            {"point_id": "abc", "titel": "Test", "datei": "test.pdf",
             "score": 0.85, "rank": 1},
        ],
        confidence="gruen",
        outcome="answered",
        answer_length=200,
        latency=LatencyBreakdown(
            rewrite_ms=50.0,
            embed_ms=100.0,
            search_ms=20.0,
            rerank_ms=500.0,
            generate_ms=2000.0,
            total_ms=2700.0,
        ),
    )
