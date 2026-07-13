"""Bestand-Tab fuer die Streamlit-Ingest-App.

Zeigt Gespeicherte Dokumente (Manifest/Dateisystem) und
Indexierte Dokumente (Qdrant) getrennt an, mit Loeschen-Buttons
und Indexierungs-Status pro Dokument.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from halle_gehirn.manifest.editor import (
    delete_manifest_entry,
    list_manifest_entries,
    load_manifest_entries,
)

_MANUAL_DIR = Path("data/manual")


def render_bestand_tab() -> None:
    """Zeigt Gespeicherte und Indexierte Dokumente getrennt."""
    # ── Gespeicherte Dokumente (Manifest / Dateisystem) ──
    st.subheader("Gespeicherte Dokumente")
    st.caption("Dokumente im Manifest (data/manifest.yaml)")

    try:
        rows = list_manifest_entries()
        entries = load_manifest_entries()
    except Exception as exc:
        st.error(f"Manifest konnte nicht geladen werden: {exc}")
        rows = []
        entries = []

    # Qdrant-Status pro Dokument abfragen
    indexed_dateien = _get_indexed_dateien()

    if not rows:
        st.info("Keine Dokumente im Manifest.")
    else:
        st.markdown(f"**{len(rows)} Dokumente** im Manifest")

        for i, (row, entry) in enumerate(zip(rows, entries)):
            datei = row["datei"]
            is_indexed = datei in indexed_dateien
            file_exists = (_MANUAL_DIR / datei).exists()

            status_icon = "🟢" if is_indexed else "⚪"
            file_icon = " ⚠️ Datei fehlt" if not file_exists else ""

            col_info, col_action = st.columns([5, 1])
            with col_info:
                st.markdown(
                    f"{status_icon} **{row['titel']}** "
                    f"(`{datei}`){file_icon}"
                )
                st.caption(
                    f"{row['doc_type']} · {row['bereich']} · "
                    f"{row['vertraulichkeit']}"
                )
            with col_action:
                if st.button(
                    "Entfernen", key=f"del_{i}",
                    help="Aus Manifest entfernen",
                ):
                    if delete_manifest_entry(datei):
                        st.success(f"'{datei}' aus Manifest entfernt.")
                        st.rerun()
                    else:
                        st.error("Eintrag nicht gefunden.")

        st.caption("🟢 = In Qdrant indexiert  ⚪ = Nicht indexiert")

    # ── Indexierte Dokumente (Qdrant) ──
    st.divider()
    _render_indexed_section(entries)


def _get_indexed_dateien() -> set[str]:
    """Holt die Liste der in Qdrant indexierten Dateien."""
    try:
        from halle_gehirn.vector_store.qdrant_client import (
            list_indexed_documents,
        )
        return {d["datei"] for d in list_indexed_documents()}
    except Exception:
        return set()


def _render_indexed_section(entries: list) -> None:
    """Zeigt die in Qdrant indexierten Dokumente."""
    st.subheader("Indexierte Dokumente")
    st.caption("Chunks in der Qdrant-Collection")

    try:
        from halle_gehirn.vector_store.qdrant_client import (
            list_indexed_documents,
        )
        indexed_docs = list_indexed_documents()
    except Exception as exc:
        st.warning(f"Qdrant nicht erreichbar: {exc}")
        return

    if not indexed_docs:
        st.info("Keine Dokumente in Qdrant indexiert.")
        return

    total_chunks = sum(d["chunk_count"] for d in indexed_docs)
    st.markdown(
        f"**{len(indexed_docs)} Dokumente** mit "
        f"**{total_chunks} Chunks** in Qdrant"
    )

    manifest_dateien = {e.datei for e in entries}

    idx_rows = []
    for doc in indexed_docs:
        in_manifest = doc["datei"] in manifest_dateien
        idx_rows.append({
            "Datei": doc["datei"],
            "Titel": doc["titel"],
            "Chunks": doc["chunk_count"],
            "Typ": doc.get("doc_type", ""),
            "Hash": doc["source_hash"][:12] + "...",
            "Im Manifest": "Ja" if in_manifest else "Nein",
        })

    df = pd.DataFrame(idx_rows)
    st.dataframe(df, width="stretch", hide_index=True)

    # Warnung bei Waisen
    orphans = [r["Datei"] for r in idx_rows if r["Im Manifest"] == "Nein"]
    if orphans:
        st.warning(
            f"{len(orphans)} Dokument(e) in Qdrant aber nicht im Manifest: "
            f"{', '.join(orphans)}"
        )
