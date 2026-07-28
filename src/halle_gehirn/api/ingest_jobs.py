"""In-Memory Job-Registry fuer asynchrone Ingest-Laeufe.

Verwaltet Ingest-Jobs als Hintergrund-Threads. SSE-Leser konsumieren
Events ueber einen Index-Cursor (append-only Liste mit Lock).

Thread-Safety: ``events``-Liste ist append-only, geschuetzt durch
``threading.Lock``. SSE-Reader nutzt Index-Cursor und liest nur
``events[seen:]``. Lock wird bei Append UND Laenge-Abfrage gehalten.
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.pipeline.indexer import IndexResult, embed_and_upsert
from halle_gehirn.pipeline.ingest import IngestStats, run_ingest
from halle_gehirn.pipeline.progress import ProgressEvent
from halle_gehirn.vector_store.qdrant_client import reset_collection

logger = structlog.get_logger(__name__)

_MAX_JOBS = 50


@dataclass
class IngestJob:
    """Ein laufender oder abgeschlossener Ingest-Job."""

    job_id: str
    status: str = "running"
    events: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.monotonic)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def append_event(self, event: dict[str, Any]) -> None:
        """Thread-sicher ein Event anhaengen."""
        with self._lock:
            self.events.append(event)

    def events_since(self, cursor: int) -> list[dict[str, Any]]:
        """Liefert Events ab Cursor-Position (thread-sicher)."""
        with self._lock:
            return list(self.events[cursor:])

    def event_count(self) -> int:
        """Aktuelle Event-Anzahl (thread-sicher)."""
        with self._lock:
            return len(self.events)


# ── Registry ──

_jobs: dict[str, IngestJob] = {}
_registry_lock = threading.Lock()


def create_job() -> str:
    """Erstellt einen neuen Job und gibt die Job-ID zurueck."""
    job_id = uuid.uuid4().hex[:12]
    job = IngestJob(job_id=job_id)
    with _registry_lock:
        if len(_jobs) >= _MAX_JOBS:
            oldest_key = min(_jobs, key=lambda k: _jobs[k].created_at)
            del _jobs[oldest_key]
        _jobs[job_id] = job
    return job_id


def get_job(job_id: str) -> IngestJob | None:
    """Liefert einen Job anhand seiner ID (oder None)."""
    with _registry_lock:
        return _jobs.get(job_id)


def start_job(
    job_id: str,
    selected_dateien: list[str],
    reset: bool = False,
    settings: Settings | None = None,
) -> None:
    """Startet den Ingest-Job als Daemon-Thread."""
    thread = threading.Thread(
        target=_run_job,
        args=(job_id, selected_dateien, reset, settings),
        daemon=True,
    )
    thread.start()


# ── Job-Runner (Thread-Target) ──


def _run_job(
    job_id: str,
    selected_dateien: list[str],
    reset: bool,
    settings: Settings | None,
) -> None:
    """Fuehrt Ingest + Embed+Upsert in einem Hintergrund-Thread aus."""
    job = get_job(job_id)
    if not job:
        return

    settings = settings or get_settings()

    try:
        if reset:
            job.append_event({
                "phase": "reset",
                "detail": "Collection wird zurueckgesetzt...",
                "datei": "",
                "doc_index": 0,
                "doc_total": len(selected_dateien),
            })
            reset_collection()

        def on_progress(event: ProgressEvent) -> None:
            job.append_event({
                "phase": event.phase,
                "datei": event.datei,
                "doc_index": event.doc_index,
                "doc_total": event.doc_total,
                "detail": event.detail,
                "chunks_so_far": event.chunks_so_far,
                "chunks_total": event.chunks_total,
                "elapsed_s": round(event.elapsed_s, 1),
            })

        payloads, ingest_stats = run_ingest(
            settings=settings,
            selected_dateien=set(selected_dateien),
            on_progress=on_progress,
        )

        if not payloads:
            job.stats = _stats_dict(ingest_stats, None)
            job.status = "completed"
            job.append_event({
                "phase": "done", "status": "completed",
                "detail": "Keine Chunks zu indexieren.",
                "datei": "", "doc_index": 0, "doc_total": 0,
                "stats": job.stats,
            })
            return

        loop = asyncio.new_event_loop()
        try:
            index_result = loop.run_until_complete(
                embed_and_upsert(
                    payloads, settings=settings, on_progress=on_progress,
                ),
            )
        finally:
            loop.close()

        job.stats = _stats_dict(ingest_stats, index_result)
        job.status = "completed"
        job.append_event({
            "phase": "done", "status": "completed",
            "detail": f"{index_result.chunks_upserted} Chunks indexiert.",
            "datei": "", "doc_index": 0, "doc_total": 0,
            "stats": job.stats,
        })

    except Exception as exc:
        logger.error("ingest_job_failed", job_id=job_id, error=str(exc))
        job.error = str(exc)
        job.status = "failed"
        job.append_event({
            "phase": "error", "status": "failed",
            "detail": str(exc),
            "datei": "", "doc_index": 0, "doc_total": 0,
        })


def _stats_dict(
    ingest: IngestStats, index: IndexResult | None,
) -> dict[str, Any]:
    """Baut ein serialisierbares Stats-Dict aus IngestStats + IndexResult."""
    result: dict[str, Any] = {
        "docs_total": ingest.docs_total,
        "docs_success": ingest.docs_success,
        "docs_skipped": ingest.docs_skipped,
        "docs_unchanged": ingest.docs_unchanged,
        "docs_failed": ingest.docs_failed,
        "chunks_total": ingest.chunks_total,
        "errors": ingest.errors,
    }
    if index:
        result["chunks_embedded"] = index.chunks_embedded
        result["chunks_upserted"] = index.chunks_upserted
        result["chunks_stale_deleted"] = index.chunks_stale_deleted
    return result
