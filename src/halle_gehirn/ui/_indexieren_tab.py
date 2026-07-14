"""Indexieren-Tab fuer die Streamlit-Ingest-App.

Ermoeglicht das selektive Indexieren von Dokumenten aus dem Manifest:
Extraktion, Chunking, Embedding und Qdrant-Upsert. Zeigt pro Dokument
den Indexierungs-Status, Fortschrittsbalken, Sample-Chunks, Abbildungen
und ETA.
"""
from __future__ import annotations

import asyncio
import logging
import queue
import threading
from io import StringIO
from pathlib import Path
from typing import Any

import streamlit as st

from halle_gehirn.config import get_settings
from halle_gehirn.manifest.editor import list_manifest_entries, load_manifest_entries
from halle_gehirn.pipeline.indexer import IndexResult, embed_and_upsert
from halle_gehirn.pipeline.ingest import IngestError, IngestStats, run_ingest
from halle_gehirn.pipeline.progress import ProgressEvent
from halle_gehirn.vector_store.qdrant_client import reset_collection

_MANUAL_DIR = Path("data/manual")


def render_indexieren_tab() -> None:
    """Rendert den Indexieren-Tab mit Dokumentauswahl."""
    st.subheader("Wissensbestand indexieren")
    st.caption(
        "Dokumente einzeln auswählen und indexieren: "
        "Extraktion, Chunking, Embedding und Qdrant-Upsert."
    )

    # Manifest laden
    try:
        rows = list_manifest_entries()
        entries = load_manifest_entries()
    except Exception as exc:
        st.warning(f"Manifest nicht lesbar: {exc}")
        return

    if not rows:
        st.info("Keine Dokumente im Manifest.")
        return

    # Indexierungs-Status aus Qdrant laden
    indexed_dateien = _get_indexed_dateien()

    # -- Dokumentauswahl --
    st.markdown(f"**{len(rows)} Dokumente** im Manifest")
    st.caption("Bereits indexierte Dokumente sind standardmäßig deaktiviert.")

    # Alle/Keine-Buttons
    col_all, col_none, col_new, _ = st.columns([1, 1, 1.5, 4.5])
    with col_all:
        if st.button("Alle auswählen"):
            for entry in entries:
                st.session_state[f"idx_{entry.datei}"] = True
            st.rerun()
    with col_none:
        if st.button("Keine auswählen"):
            for entry in entries:
                st.session_state[f"idx_{entry.datei}"] = False
            st.rerun()
    with col_new:
        if st.button("Nur neue auswählen"):
            for entry in entries:
                st.session_state[f"idx_{entry.datei}"] = (
                    entry.datei not in indexed_dateien
                )
            st.rerun()

    # Dokument-Checkboxen
    selected_dateien: set[str] = set()
    for row, entry in zip(rows, entries, strict=True):
        datei = entry.datei
        is_indexed = datei in indexed_dateien
        file_exists = (_MANUAL_DIR / datei).exists()

        status_label = "indexiert" if is_indexed else "neu"
        status_icon = "🟢" if is_indexed else "⚪"
        file_warn = " — Datei fehlt!" if not file_exists else ""

        # Default: neue Dokumente ausgewaehlt, indexierte nicht
        default = not is_indexed
        checked = st.checkbox(
            f"{status_icon} {row['titel']}  "
            f"(`{datei}`) [{status_label}]{file_warn}",
            value=default,
            key=f"idx_{datei}",
        )
        if checked:
            selected_dateien.add(datei)

    # Auswahl-Statistik
    n_selected = len(selected_dateien)
    n_new = sum(1 for d in selected_dateien if d not in indexed_dateien)
    n_reindex = n_selected - n_new
    if n_selected:
        parts = [f"**{n_selected} Dokumente** ausgewählt"]
        if n_new:
            parts.append(f"{n_new} neue")
        if n_reindex:
            parts.append(f"{n_reindex} erneut indexieren")
        st.info(" — ".join(parts))
    else:
        st.warning("Keine Dokumente ausgewählt.")

    # Reset-Checkbox
    do_reset = st.checkbox(
        "Collection zurücksetzen",
        help="Löscht die bestehende Qdrant-Collection und erstellt sie neu.",
    )
    if do_reset:
        st.warning("Die gesamte Collection wird gelöscht und neu aufgebaut!")

    # Indexieren-Button
    if st.button(
        "Indexieren starten",
        type="primary",
        disabled=n_selected == 0,
    ):
        _run_indexing(do_reset, selected_dateien)


def _get_indexed_dateien() -> set[str]:
    """Holt die Liste der in Qdrant indexierten Dateien."""
    try:
        from halle_gehirn.vector_store.qdrant_client import (
            list_indexed_documents,
        )
        return {d["datei"] for d in list_indexed_documents()}
    except Exception:
        return set()


def _run_indexing(do_reset: bool, selected_dateien: set[str]) -> None:
    """Fuehrt den Indexierungslauf durch mit Log-Capture."""
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    try:
        _run_indexing_inner(do_reset, selected_dateien)
    finally:
        root_logger.removeHandler(handler)

    # Logs anzeigen
    log_text = log_stream.getvalue()
    if log_text.strip():
        with st.expander("Detaillierte Logs", expanded=False):
            st.code(log_text, language="text")


def _run_indexing_inner(
    do_reset: bool, selected_dateien: set[str],
) -> None:
    """Kern-Logik des Indexierungslaufs mit detailliertem Fortschritt."""
    # Schritt 1: Reset (optional)
    if do_reset:
        with st.spinner("Collection wird zurückgesetzt..."):
            try:
                reset_collection()
                st.success("Collection zurückgesetzt.")
            except Exception as exc:
                st.error(f"Collection-Reset fehlgeschlagen: {exc}")
                _show_connection_hint(exc)
                return

    # Schritt 2: Ingest (Extract + Chunk) mit Fortschritt
    progress_bar = st.progress(0.0, text="Starte Extraktion...")
    timing_placeholder = st.empty()
    doc_container = st.container()

    # Fortschritts-State fuer den Callback
    last_doc: dict[str, str] = {}

    def _ingest_progress(event: ProgressEvent) -> None:
        """Callback: rendert Ingest-Fortschritt in Streamlit."""
        if event.doc_total > 0:
            pct = event.doc_index / event.doc_total
            progress_bar.progress(
                min(pct, 1.0),
                text=(
                    f"Dokument {event.doc_index}/{event.doc_total} "
                    f"— {event.datei}"
                ),
            )

        # Timing / ETA
        elapsed = event.elapsed_s
        if event.doc_index > 0 and event.doc_total > 0:
            per_doc = elapsed / event.doc_index
            remaining = per_doc * (event.doc_total - event.doc_index)
            timing_placeholder.caption(
                f"{elapsed:.0f}s vergangen "
                f"— ca. {remaining:.0f}s verbleibend "
                f"— {event.chunks_so_far} Chunks bisher"
            )
        elif elapsed > 0:
            timing_placeholder.caption(f"{elapsed:.0f}s vergangen")

        # Per-Dokument-Details (nur bei neuem Dokument nach Chunking)
        if event.phase == "chunk" and event.datei != last_doc.get("datei"):
            last_doc["datei"] = event.datei
            with doc_container:
                _render_doc_progress(event)

        if event.phase == "enrich":
            progress_bar.progress(1.0, text="Kontextanreicherung...")

    try:
        payloads, stats = run_ingest(
            selected_dateien=selected_dateien,
            on_progress=_ingest_progress,
        )
    except IngestError as exc:
        st.error(f"Ingest fehlgeschlagen: {exc}")
        return

    progress_bar.progress(1.0, text="Extraktion abgeschlossen")
    _show_ingest_stats(stats)

    if not payloads:
        st.warning("Keine Chunks erzeugt — Indexierung übersprungen.")
        return

    # Schritt 3: Embed + Upsert (im Thread, Fortschritt via Queue)
    embed_bar = st.progress(0.0, text="Starte Embedding...")
    embed_status = st.empty()

    try:
        result = _run_async_embed_with_progress(
            payloads, embed_bar, embed_status,
        )
    except Exception as exc:
        st.error(f"Embedding/Upsert fehlgeschlagen: {exc}")
        _show_connection_hint(exc)
        return

    embed_bar.progress(1.0, text="Embedding + Upsert abgeschlossen")
    st.success(
        f"Indexierung abgeschlossen: "
        f"{result.chunks_upserted} Chunks in Qdrant geschrieben."
    )


def _render_doc_progress(event: ProgressEvent) -> None:
    """Rendert den Fortschritt eines einzelnen Dokuments."""
    label = (
        f"**{event.datei}** — "
        f"{event.chunks_total} Chunks"
    )
    if event.figures_count:
        label += f" — {event.figures_count} Abbildungen"

    with st.expander(label, expanded=False):
        # Strategie
        if event.strategy:
            st.caption(f"Chunking: {event.strategy}")

        # Sample-Chunk
        if event.sample_chunk:
            heading = event.sample_heading or "(kein Heading)"
            st.markdown(f"**Sample-Chunk** [{heading}]:")
            st.code(event.sample_chunk, language="text")

        # Abbildungen (Thumbnails)
        if event.figure_paths:
            figures_dir = Path(get_settings().figures_dir)
            cols = st.columns(min(len(event.figure_paths), 3))
            for i, fig_path in enumerate(event.figure_paths):
                img = figures_dir / fig_path
                if img.is_file():
                    with cols[i % len(cols)]:
                        st.image(str(img), width=200)


def _run_async_embed_with_progress(
    payloads: list,
    progress_bar: Any,
    status_placeholder: Any,
) -> IndexResult:
    """Fuehrt embed_and_upsert in einem Thread mit Queue-Fortschritt aus."""
    q: queue.Queue[ProgressEvent | None] = queue.Queue()
    result_holder: list[IndexResult] = []
    error_holder: list[Exception] = []

    def _on_progress(event: ProgressEvent) -> None:
        q.put(event)

    def _thread_target() -> None:
        loop = asyncio.new_event_loop()
        try:
            r = loop.run_until_complete(
                embed_and_upsert(payloads, on_progress=_on_progress),
            )
            result_holder.append(r)
        except Exception as exc:
            error_holder.append(exc)
        finally:
            loop.close()
            q.put(None)  # Sentinel

    thread = threading.Thread(target=_thread_target)
    thread.start()

    # Events aus der Queue pollen und rendern
    phases_seen = 0
    total_phases = 3  # dense, sparse, upsert
    while True:
        try:
            event = q.get(timeout=0.5)
        except queue.Empty:
            if not thread.is_alive():
                break
            continue
        if event is None:
            break
        phases_seen += 1
        pct = min(phases_seen / total_phases, 1.0)
        progress_bar.progress(pct, text=event.detail)
        status_placeholder.caption(event.detail)

    thread.join()
    if error_holder:
        raise error_holder[0]
    return result_holder[0]


def _show_ingest_stats(stats: IngestStats) -> None:
    """Zeigt Ingest-Statistiken im UI an."""
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Gesamt", stats.docs_total)
    c2.metric("Erfolgreich", stats.docs_success)
    c3.metric("Übersprungen", stats.docs_skipped)
    c4.metric("Fehlgeschlagen", stats.docs_failed)
    st.metric("Chunks erzeugt", stats.chunks_total)

    if stats.errors:
        with st.expander(f"{len(stats.errors)} Fehler/Warnungen"):
            for err in stats.errors:
                st.text(err)


def _show_connection_hint(exc: Exception) -> None:
    """Zeigt Hinweise bei Verbindungsfehlern."""
    msg = str(exc).lower()
    if "connection" not in msg and "refused" not in msg and "timeout" not in msg:
        return
    if "11434" in msg or "ollama" in msg:
        st.info("Hinweis: Ist Ollama gestartet? (ollama serve)")
    elif "6335" in msg or "qdrant" in msg:
        st.info("Hinweis: Ist Qdrant gestartet? (docker-compose up qdrant)")
