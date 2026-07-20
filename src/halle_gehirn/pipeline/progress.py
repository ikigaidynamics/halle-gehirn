"""Progress-Events fuer die Ingest-Pipeline.

Definiert ``ProgressEvent`` und den Callback-Typ, den ``run_ingest``
und ``embed_and_upsert`` optional akzeptieren. Die Streamlit-UI
registriert einen Callback, der die Events in Echtzeit rendert.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class ProgressEvent:
    """Ein Fortschrittsereignis waehrend der Indexierung."""

    phase: str
    """Phase: ``extract``, ``chunk``, ``enrich``, ``embed``, ``upsert``."""
    datei: str
    """Dateiname des aktuellen Dokuments."""
    doc_index: int
    """1-basierter Index des aktuellen Dokuments."""
    doc_total: int
    """Gesamtzahl der Dokumente."""
    detail: str
    """Menschenlesbarer Fortschrittstext."""

    # Optionale Detail-Daten
    chunks_so_far: int = 0
    chunks_total: int = 0
    sample_chunk: str | None = None
    sample_heading: str | None = None
    strategy: str | None = None
    figures_count: int = 0
    figure_paths: list[str] = field(default_factory=list)
    elapsed_s: float = 0.0

    # Erweiterte Metadaten fuer detailliertere Fortschrittsanzeige
    body_chars: int = 0
    tables_count: int = 0
    chunks_before_filter: int = 0
    extraction_backend: str | None = None
    ocr_retry: bool = False
    file_size_bytes: int = 0


ProgressCallback = Callable[[ProgressEvent], None] | None
"""Optionaler Callback fuer Fortschrittsereignisse."""
