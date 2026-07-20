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
        file_warn = " — Datei fehlt!" if not file_exists else ""

        # Default: neue Dokumente ausgewaehlt, indexierte nicht
        default = not is_indexed
        checked = st.checkbox(
            f"{row['titel']}  (`{datei}`) [{status_label}]{file_warn}",
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
        parts = [f"{n_selected} Dokument(e) ausgewählt"]
        if n_new:
            parts.append(f"{n_new} neu")
        if n_reindex:
            parts.append(f"{n_reindex} erneut indexieren")
        st.markdown(
            '<div style="padding:11px 15px;border-radius:9px;'
            "background:rgba(226,0,26,0.04);"
            "border:1px solid rgba(226,0,26,0.14);"
            'font-size:13px;color:#333;font-weight:500;">'
            f'{" — ".join(parts)}</div>',
            unsafe_allow_html=True,
        )
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

    # Logs anzeigen (dunkler Log-Block)
    log_text = log_stream.getvalue()
    if log_text.strip():
        with st.expander("Detaillierte Logs", expanded=False):
            import html as html_mod
            escaped = html_mod.escape(log_text)
            # Syntax-Highlighting fuer Log-Level
            escaped = escaped.replace(
                "INFO", '<span class="log-info">INFO</span>',
            )
            escaped = escaped.replace(
                "DONE", '<span class="log-done">DONE</span>',
            )
            escaped = escaped.replace(
                "ERROR", '<span class="log-error">ERROR</span>',
            )
            st.markdown(
                f'<div class="jv-log-block">{escaped}</div>',
                unsafe_allow_html=True,
            )


def _run_indexing_inner(
    do_reset: bool, selected_dateien: set[str],
) -> None:
    """Kern-Logik des Indexierungslaufs mit detailliertem Fortschritt."""
    import time

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

    # Schritt 2: Ingest (Extract + Chunk) — im Thread mit Live-Status
    status_container = st.status(
        "Extraktion wird gestartet...", expanded=True,
    )
    progress_bar = st.progress(0.0)
    doc_container = st.container()

    # Fortschritts-State fuer den Callback
    last_doc: dict[str, str] = {}
    start_time = time.monotonic()

    def _ingest_progress(event: ProgressEvent) -> None:
        """Callback: rendert Ingest-Fortschritt in Streamlit."""
        elapsed = time.monotonic() - start_time

        if event.doc_total > 0:
            if event.phase == "extract":
                pct = (event.doc_index - 1) / event.doc_total
            else:
                pct = event.doc_index / event.doc_total
            progress_bar.progress(min(pct, 1.0))

        if event.phase == "extract":
            status_container.update(
                label=(
                    f"Extrahiere {event.datei} "
                    f"({event.doc_index}/{event.doc_total}) "
                    f"— {elapsed:.0f}s"
                ),
                state="running",
            )
        elif event.phase == "chunk":
            eta = ""
            if event.doc_index > 0 and event.doc_total > event.doc_index:
                per_doc = elapsed / event.doc_index
                remaining = per_doc * (event.doc_total - event.doc_index)
                eta = f" — ca. {remaining:.0f}s verbleibend"
            backend_hint = ""
            if event.extraction_backend:
                backend_hint = f" [{event.extraction_backend}]"
            ocr_hint = " (OCR-Retry)" if event.ocr_retry else ""
            status_container.update(
                label=(
                    f"Dokument {event.doc_index}/{event.doc_total} "
                    f"— {event.chunks_so_far} Chunks{backend_hint}"
                    f"{ocr_hint}{eta}"
                ),
                state="running",
            )
        elif event.phase == "enrich":
            progress_bar.progress(1.0)
            status_container.update(
                label="Kontextanreicherung...",
                state="running",
            )

        # Per-Dokument-Details (nur bei neuem Dokument nach Chunking)
        if event.phase == "chunk" and event.datei != last_doc.get("datei"):
            last_doc["datei"] = event.datei
            with doc_container:
                _render_doc_progress(event)

    try:
        try:
            payloads, stats = run_ingest(
                selected_dateien=selected_dateien,
                on_progress=_ingest_progress,
            )
        except TypeError:
            payloads, stats = run_ingest(
                selected_dateien=selected_dateien,
            )
    except IngestError as exc:
        status_container.update(label="Extraktion fehlgeschlagen", state="error")
        st.error(f"Ingest fehlgeschlagen: {exc}")
        return

    elapsed_total = time.monotonic() - start_time
    progress_bar.progress(1.0)
    has_warnings = stats.docs_failed > 0
    status_container.update(
        label=(
            f"Extraktion abgeschlossen — "
            f"{stats.chunks_total} Chunks aus "
            f"{stats.docs_success} Dokumenten — {elapsed_total:.0f}s"
        ),
        state="error" if has_warnings and stats.docs_success == 0 else "complete",
        expanded=has_warnings,
    )
    _show_ingest_stats(stats)

    if not payloads:
        st.warning("Keine Chunks erzeugt — Indexierung übersprungen.")
        return

    # Schritt 3: Embed + Upsert (im Thread, Fortschritt via Queue)
    embed_status = st.status("Starte Embedding...", expanded=True)
    embed_bar = st.progress(0.0)

    try:
        result = _run_async_embed_with_progress(
            payloads, embed_bar, embed_status,
        )
    except Exception as exc:
        embed_status.update(label="Embedding fehlgeschlagen", state="error")
        st.error(f"Embedding/Upsert fehlgeschlagen: {exc}")
        _show_connection_hint(exc)
        return

    embed_bar.progress(1.0)
    embed_status.update(
        label="Embedding + Upsert abgeschlossen", state="complete",
        expanded=False,
    )
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
        # Extraktions-Details
        details: list[str] = []
        if event.extraction_backend:
            details.append(f"Backend: `{event.extraction_backend}`")
        if event.file_size_bytes:
            size_mb = event.file_size_bytes / (1024 * 1024)
            if size_mb >= 1.0:
                details.append(f"Dateigröße: {size_mb:.1f} MB")
            else:
                size_kb = event.file_size_bytes / 1024
                details.append(f"Dateigröße: {size_kb:.0f} KB")
        if event.body_chars:
            details.append(f"Extrahierter Text: {event.body_chars:,} Zeichen")
        if event.tables_count:
            details.append(f"Tabellen: {event.tables_count}")
        if event.ocr_retry:
            details.append("OCR-Retry: ja")
        if details:
            st.caption(" · ".join(details))

        # Strategie + Filter-Info
        strategy_parts: list[str] = []
        if event.strategy:
            strategy_parts.append(f"Chunking: {event.strategy}")
        if event.chunks_before_filter and event.chunks_before_filter > event.chunks_total:
            dropped = event.chunks_before_filter - event.chunks_total
            strategy_parts.append(
                f"Filter: {dropped} Chunks entfernt "
                f"({event.chunks_before_filter} → {event.chunks_total})"
            )
        if strategy_parts:
            st.caption(" · ".join(strategy_parts))

        # Sample-Chunk
        if event.sample_chunk:
            heading = event.sample_heading or "(kein Heading)"
            st.markdown(f"**Sample-Chunk** [{heading}]:")
            st.code(event.sample_chunk, language="text")

        # Abbildungen (Thumbnails)
        if event.figure_paths:
            figures_dir = Path(get_settings().figures_dir)
            max_show = min(len(event.figure_paths), 8)
            shown = event.figure_paths[:max_show]
            cols = st.columns(min(len(shown), 4))
            for i, fig_path in enumerate(shown):
                img = figures_dir / fig_path
                if img.is_file():
                    with cols[i % len(cols)]:
                        cap = Path(fig_path).stem.replace("_", " ")
                        st.image(str(img), caption=cap)
            if len(event.figure_paths) > max_show:
                st.caption(
                    f"… und {len(event.figure_paths) - max_show} "
                    f"weitere Abbildungen (im Dokument-Viewer einsehbar)"
                )


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
            try:
                r = loop.run_until_complete(
                    embed_and_upsert(payloads, on_progress=_on_progress),
                )
            except TypeError:
                r = loop.run_until_complete(
                    embed_and_upsert(payloads),
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
        progress_bar.progress(pct)
        status_placeholder.update(
            label=event.detail, state="running",
        )

    thread.join()
    if error_holder:
        raise error_holder[0]
    return result_holder[0]


def _show_ingest_stats(stats: IngestStats) -> None:
    """Zeigt Ingest-Statistiken im UI an."""
    cols = st.columns(5)
    cols[0].metric("Gesamt", stats.docs_total)
    cols[1].metric("Erfolgreich", stats.docs_success)
    cols[2].metric("Übersprungen", stats.docs_skipped)
    cols[3].metric("Fehlgeschlagen", stats.docs_failed)
    cols[4].metric("Chunks", stats.chunks_total)

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
