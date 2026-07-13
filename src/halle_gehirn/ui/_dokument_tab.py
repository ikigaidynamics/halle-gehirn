"""Dokument-Viewer + Chunk-Inspektion fuer die Ingest-App.

Zeigt den Inhalt eines ausgewaehlten Dokuments und (falls indexiert)
die zugehoerigen Chunks mit allen Metadaten — aehnlich dem
Qdrant-Dashboard, aber direkt in der Streamlit-UI.
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import streamlit as st

from halle_gehirn.manifest.editor import load_manifest_entries

_MANUAL_DIR = Path("data/manual")

# Metadaten-Felder, die in der Chunk-Ansicht angezeigt werden
_META_DISPLAY_FIELDS = [
    "chunk_index",
    "char_start",
    "char_end",
    "page",
    "breadcrumb",
    "context_prefix",
    "source_hash",
    "datei",
    "titel",
    "doc_type",
    "bereich",
    "thema",
    "anlage",
    "herkunft",
    "quelltyp",
    "vertraulichkeit",
    "status",
    "jahr",
    "projekt",
    "ansprechperson",
]


def render_dokument_tab() -> None:
    """Rendert den Dokument-Viewer-Tab."""
    st.subheader("Dokument-Viewer")
    st.caption(
        "Dokument anzeigen und Chunks mit Metadaten inspizieren"
    )

    try:
        entries = load_manifest_entries()
    except Exception as exc:
        st.error(f"Manifest konnte nicht geladen werden: {exc}")
        return

    if not entries:
        st.info("Keine Dokumente im Manifest.")
        return

    # ── Dokument-Auswahl ──
    options = {e.datei: e.titel for e in entries}
    selected = st.selectbox(
        "Dokument auswählen",
        options=list(options.keys()),
        format_func=lambda d: f"{options[d]}  ({d})",
    )

    if not selected:
        return

    entry = next(e for e in entries if e.datei == selected)

    # ── Metadaten-Uebersicht ──
    with st.expander("Manifest-Metadaten", expanded=False):
        meta_cols = st.columns(3)
        with meta_cols[0]:
            st.markdown(f"**Titel:** {entry.titel}")
            st.markdown(f"**Typ:** {entry.doc_type}")
            st.markdown(f"**Bereich:** {', '.join(entry.bereich)}")
        with meta_cols[1]:
            st.markdown(f"**Herkunft:** {entry.herkunft}")
            st.markdown(f"**Quelltyp:** {entry.quelltyp}")
            st.markdown(f"**Vertraulichkeit:** {entry.vertraulichkeit}")
        with meta_cols[2]:
            st.markdown(f"**Jahr:** {entry.jahr or '—'}")
            st.markdown(f"**Status:** {entry.status}")
            if entry.grad:
                st.markdown(f"**Grad:** {entry.grad}")

    # ── Dokumentinhalt ──
    st.divider()
    _render_document_content(selected)

    # ── Chunk-Ansicht ──
    st.divider()
    _render_chunks(selected)


def _render_document_content(datei: str) -> None:
    """Zeigt den Dokumentinhalt an."""
    st.subheader("Dokumentinhalt")

    file_path = _MANUAL_DIR / datei
    if not file_path.exists():
        st.warning(f"Datei nicht gefunden: {file_path}")
        return

    suffix = file_path.suffix.lower()

    if suffix == ".md":
        content = _read_text_file(file_path)
        if content:
            st.markdown(content)
    elif suffix == ".txt":
        content = _read_text_file(file_path)
        if content:
            st.text(content)
    elif suffix == ".pdf":
        st.info(
            "PDF-Vorschau: Nur der extrahierte Text wird angezeigt. "
            "Starte die Indexierung, um den vollstaendigen Text zu sehen."
        )
        # Versuche PlaintextExtractor (nur fuer .md/.txt)
        # Fuer PDFs zeigen wir einen Hinweis
        st.caption(f"Datei: {file_path} ({file_path.stat().st_size:,} Bytes)")
    else:
        st.caption(
            f"Vorschau nicht verfuegbar fuer {suffix}-Dateien. "
            f"Datei: {file_path}"
        )


def _read_text_file(path: Path) -> str | None:
    """Liest eine Textdatei (UTF-8, Fallback latin-1)."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="latin-1")
        except Exception:
            return None
    except Exception:
        return None


def _render_chunks(datei: str) -> None:
    """Zeigt alle Chunks eines Dokuments mit Metadaten."""
    st.subheader("Chunks in Qdrant")

    try:
        from halle_gehirn.vector_store.qdrant_client import (
            get_chunks_by_datei,
        )
        chunks = get_chunks_by_datei(datei)
    except Exception as exc:
        st.warning(f"Qdrant nicht erreichbar: {exc}")
        return

    if not chunks:
        st.info(
            "Keine Chunks fuer dieses Dokument in Qdrant. "
            "Bitte zuerst indexieren."
        )
        return

    st.markdown(f"**{len(chunks)} Chunks** indexiert")

    for chunk in chunks:
        payload = chunk["payload"]
        idx = payload.get("chunk_index", "?")
        text_raw = payload.get("text_raw", "") or payload.get("text", "")
        char_count = len(text_raw)

        label = (
            f"Chunk {idx}  |  {char_count} Zeichen  |  "
            f"ID: {chunk['point_id'][:12]}..."
        )

        with st.expander(label, expanded=False):
            # ── Chunk-Text ──
            st.markdown("**Text:**")
            escaped = html.escape(text_raw)
            st.markdown(
                f'<div style="white-space: pre-wrap; font-size: 0.9em;'
                f" color: #333; background: #f8f9fa; padding: 10px;"
                f' border-radius: 6px; border-left: 3px solid #0066cc;'
                f' max-height: 400px; overflow-y: auto;">'
                f"{escaped}</div>",
                unsafe_allow_html=True,
            )

            # ── Context-Prefix (falls vorhanden) ──
            ctx = payload.get("context_prefix", "")
            if ctx:
                st.markdown("**Context-Prefix:**")
                ctx_escaped = html.escape(ctx)
                st.markdown(
                    f'<div style="white-space: pre-wrap; font-size: 0.85em;'
                    f" color: #666; background: #fff3cd; padding: 8px;"
                    f' border-radius: 4px; font-style: italic;">'
                    f"{ctx_escaped}</div>",
                    unsafe_allow_html=True,
                )

            # ── Metadaten-Tabelle ──
            st.markdown("**Metadaten:**")
            meta_items: list[dict[str, str]] = []
            for field in _META_DISPLAY_FIELDS:
                val = payload.get(field)
                if val is None or val == "" or field in ("context_prefix",):
                    continue
                if isinstance(val, list):
                    val = ", ".join(str(v) for v in val)
                meta_items.append({
                    "Feld": field,
                    "Wert": str(val),
                })

            if meta_items:
                _render_meta_table(meta_items)


def _render_meta_table(items: list[dict[str, str]]) -> None:
    """Rendert Metadaten als kompakte HTML-Tabelle."""
    rows_html = ""
    for item in items:
        key = html.escape(item["Feld"])
        val = html.escape(item["Wert"])
        rows_html += (
            f"<tr>"
            f'<td style="padding: 4px 8px; font-weight: 600; '
            f'background: #f0f0f0; border: 1px solid #ddd;">{key}</td>'
            f'<td style="padding: 4px 8px; border: 1px solid #ddd; '
            f'font-family: monospace; font-size: 0.85em;">{val}</td>'
            f"</tr>"
        )
    st.markdown(
        f'<table style="border-collapse: collapse; width: 100%; '
        f'margin-top: 4px;">{rows_html}</table>',
        unsafe_allow_html=True,
    )
