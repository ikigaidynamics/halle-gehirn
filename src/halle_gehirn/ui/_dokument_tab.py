"""Dokument-Viewer + Chunk-Inspektion fuer die Ingest-App.

Zeigt den Inhalt eines ausgewaehlten Dokuments und (falls indexiert)
die zugehoerigen Chunks mit allen Metadaten — aehnlich dem
Qdrant-Dashboard, aber direkt in der Streamlit-UI.
"""
from __future__ import annotations

import hashlib
import html
from pathlib import Path
from typing import Any

import streamlit as st

from halle_gehirn.manifest.editor import load_manifest_entries, resolve_label
from halle_gehirn.ui._display_helpers import (
    clean_snippet,
    md_lists_to_html,
    render_meta_table,
)

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
    "autor",
]

# Menschenlesbare Feldnamen fuer die Chunk-Metadaten-Tabelle
_FIELD_LABELS: dict[str, str] = {
    "chunk_index": "Chunk-Nr.",
    "char_start": "Zeichen ab",
    "char_end": "Zeichen bis",
    "page": "Seite",
    "breadcrumb": "Abschnitt",
    "context_prefix": "Kontext-Prefix",
    "source_hash": "Quell-Hash",
    "datei": "Datei",
    "titel": "Titel",
    "doc_type": "Dokumenttyp",
    "bereich": "Bereich",
    "thema": "Thema",
    "anlage": "Anlage",
    "herkunft": "Herkunft",
    "quelltyp": "Quelltyp",
    "vertraulichkeit": "Vertraulichkeit",
    "status": "Status",
    "jahr": "Jahr",
    "projekt": "Projekt",
    "ansprechperson": "Ansprechperson",
    "autor": "Autor",
}


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
            st.markdown(f"**Typ:** {resolve_label(entry.doc_type)}")
            bereich_labels = ", ".join(
                resolve_label(b) for b in entry.bereich
            )
            st.markdown(f"**Bereich:** {bereich_labels}")
        with meta_cols[1]:
            st.markdown(f"**Herkunft:** {resolve_label(entry.herkunft)}")
            st.markdown(f"**Quelltyp:** {resolve_label(entry.quelltyp)}")
            st.markdown(f"**Vertraulichkeit:** {resolve_label(entry.vertraulichkeit)}")
        with meta_cols[2]:
            st.markdown(f"**Jahr:** {entry.jahr or '—'}")
            st.markdown(f"**Status:** {resolve_label(entry.status)}")
            if entry.grad:
                st.markdown(f"**Grad:** {resolve_label(entry.grad)}")

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
        _render_pdf_figures(file_path)
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


def _render_pdf_figures(file_path: Path) -> None:
    """Zeigt extrahierte Abbildungen aus einer PDF-Datei."""
    from halle_gehirn.config import get_settings

    fig_paths = _find_figures_for_file(
        file_path, Path(get_settings().figures_dir),
    )
    if fig_paths:
        st.markdown(f"**{len(fig_paths)} Abbildung(en) extrahiert:**")
        for fig_path in fig_paths:
            caption = fig_path.stem.replace("_", " ").title()
            try:
                st.image(str(fig_path), caption=caption)
            except Exception as exc:
                st.warning(f"Bild konnte nicht geladen werden: {exc}")
    else:
        st.info(
            "Keine extrahierten Abbildungen gefunden. "
            "Bitte zuerst indexieren, um Abbildungen zu extrahieren."
        )


def _find_figures_for_file(
    file_path: Path, figures_dir: Path,
) -> list[Path]:
    """Sucht extrahierte Abbildungen fuer eine Datei via Source-Hash."""
    if not figures_dir.exists():
        return []
    h = hashlib.sha256()
    try:
        with file_path.open("rb") as f:
            for block in iter(lambda: f.read(8192), b""):
                h.update(block)
    except OSError:
        return []
    hash_dir = figures_dir / h.hexdigest()[:16]
    if not hash_dir.exists():
        return []
    return sorted(hash_dir.glob("*.png"))


def _render_chunks(datei: str) -> None:
    """Zeigt alle Chunks eines Dokuments mit Metadaten."""
    st.subheader("Chunks in Qdrant")

    try:
        from halle_gehirn.vector_store.qdrant_client import (
            delete_points_by_ids,
            get_chunks_by_datei,
            update_point_payload,
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
            cleaned = clean_snippet(text_raw)
            escaped = html.escape(cleaned)
            formatted = md_lists_to_html(escaped)
            st.markdown(
                f'<div style="white-space: pre-wrap; font-size: 0.9em;'
                f" color: #333; background: #f8f9fa; padding: 10px;"
                f' border-radius: 6px; border-left: 3px solid #0066cc;'
                f' max-height: 400px; overflow-y: auto;">'
                f"{formatted}</div>",
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
                    val = ", ".join(
                        resolve_label(str(v)) for v in val
                    )
                else:
                    val = resolve_label(str(val))
                meta_items.append({
                    "Feld": _FIELD_LABELS.get(field, field),
                    "Wert": str(val),
                })

            if meta_items:
                render_meta_table(meta_items)

            # ── Aktionen (Loeschen / Bearbeiten) ──
            _render_chunk_actions(
                chunk, idx, text_raw,
                delete_points_by_ids, update_point_payload,
            )


def _render_chunk_actions(
    chunk: dict[str, Any],
    idx: Any,
    text_raw: str,
    delete_fn: Any,
    update_fn: Any,
) -> None:
    """Rendert Loeschen- und Bearbeiten-Buttons fuer einen Chunk.

    Args:
        chunk: Chunk-Dict mit point_id und payload.
        idx: Chunk-Index (fuer Labels).
        text_raw: Roher Chunk-Text.
        delete_fn: Funktion zum Loeschen (delete_points_by_ids).
        update_fn: Funktion zum Aktualisieren (update_point_payload).
    """
    pid = chunk["point_id"]
    st.markdown("---")
    cols = st.columns([1, 1, 4])
    with cols[0]:
        if st.button("Loeschen", key=f"del_{pid}", type="secondary"):
            delete_fn([pid])
            st.success(f"Chunk {idx} geloescht.")
            st.rerun()
    with cols[1]:
        edit_key = f"editing_{pid}"
        if st.button("Bearbeiten", key=f"edit_{pid}", type="secondary"):
            st.session_state[edit_key] = True

    if st.session_state.get(f"editing_{pid}", False):
        new_text = st.text_area(
            "Text bearbeiten",
            value=text_raw,
            key=f"textarea_{pid}",
            height=200,
        )
        save_cols = st.columns([1, 5])
        with save_cols[0]:
            if st.button("Speichern", key=f"save_{pid}", type="primary"):
                update_fn(pid, {"text": new_text, "text_raw": new_text})
                st.session_state[f"editing_{pid}"] = False
                st.warning(
                    "Text aktualisiert. Der Embedding-Vektor bleibt "
                    "unveraendert — fuer volle Aktualisierung bitte "
                    "neu indexieren."
                )
                st.rerun()


