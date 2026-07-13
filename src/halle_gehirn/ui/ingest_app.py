"""Streamlit-Tool: Manifest-Editor + Bestandsuebersicht.

Separates Tool zur Pflege des Wissensbestands. NICHT die Chat-Demo
(``streamlit_app.py``). Enthaelt Manifest-Editor mit Auto-Erkennung
von Metadaten beim Upload, Bestandsuebersicht und Indexierung.

Starten: ``streamlit run src/halle_gehirn/ui/ingest_app.py``
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from halle_gehirn.extraction.metadata_detector import (
    MetadataSuggestion,
    detect_metadata,
    extract_text_from_upload,
)
from halle_gehirn.manifest.editor import (
    list_upload_sorten,
    load_vokabular_choices,
)
from halle_gehirn.ui._bestand_tab import render_bestand_tab
from halle_gehirn.ui._dokument_tab import render_dokument_tab
from halle_gehirn.ui._indexieren_tab import render_indexieren_tab
from halle_gehirn.ui._neu_tab_helpers import handle_save, render_vokabular_form

_ALLOWED_EXTENSIONS = ["pdf", "docx", "pptx", "xlsx", "md", "txt"]
_PUBLIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "public"


def main() -> None:
    """Hauptfunktion der Ingest-App."""
    icon_path = _PUBLIC_DIR / "MD_Icon_bg.jpg"
    st.set_page_config(
        page_title="Jarvis — Wissensbestand",
        page_icon=str(icon_path) if icon_path.exists() else None,
        layout="wide",
    )

    # ── Header mit MDZ-Branding ──
    _render_branding_header()

    tab_bestand, tab_neu, tab_viewer, tab_index = st.tabs(
        ["Bestand", "Neues Dokument", "Dokument-Viewer", "Indexieren"],
    )

    with tab_bestand:
        render_bestand_tab()

    with tab_neu:
        _render_neu_tab()

    with tab_viewer:
        render_dokument_tab()

    with tab_index:
        render_indexieren_tab()


# ────────────────────────── Branding ──────────────────────────


def _render_branding_header() -> None:
    """Zeigt MDZ-Logo und Titel."""
    logo_path = _PUBLIC_DIR / "MD_zentrum_Spreeland.png"
    col_logo, col_title = st.columns([1, 3])
    with col_logo:
        if logo_path.exists():
            st.image(str(logo_path), width=200)
    with col_title:
        st.title("Jarvis — Wissensbestand")
        st.caption(
            "Dokumentenverwaltung & Indexierung · "
            "Mittelstand-Digital Zentrum Spreeland"
        )


# ────────────────────────── Tab: Neu ──────────────────────────


def _find_index(options: list[str], value: str | None) -> int | None:
    """Index eines Werts in der Optionsliste, None fuer Placeholder."""
    if value is None:
        return None
    try:
        return options.index(value)
    except ValueError:
        return None


def _run_detection(uploaded: Any, choices: dict[str, dict[str, str]]) -> None:
    """Fuehrt Metadaten-Erkennung bei neuem Upload aus."""
    if uploaded is None:
        if "_meta_suggestion" in st.session_state:
            del st.session_state["_meta_suggestion"]
            st.session_state.pop("_detected_filename", None)
            st.session_state["_form_version"] = (
                st.session_state.get("_form_version", 0) + 1
            )
        return

    prev = st.session_state.get("_detected_filename")
    if prev == uploaded.name:
        return

    with st.spinner("Dokument wird analysiert..."):
        file_data: bytes = uploaded.read()
        uploaded.seek(0)
        text = extract_text_from_upload(file_data, uploaded.name)
        sug = detect_metadata(uploaded.name, text, choices)

    st.session_state["_meta_suggestion"] = sug
    st.session_state["_detected_filename"] = uploaded.name
    st.session_state["_form_version"] = (
        st.session_state.get("_form_version", 0) + 1
    )


def _render_neu_tab() -> None:
    """Formular zum Anlegen eines neuen Manifest-Eintrags."""
    choices = load_vokabular_choices()
    sorten = list_upload_sorten()

    if not sorten:
        st.error("Keine Sorten-Verzeichnisse unter data/manual/ gefunden.")
        return

    # ── Datei-Upload ──
    st.subheader("Dokument hochladen")
    uploaded = st.file_uploader(
        "Datei wählen",
        type=_ALLOWED_EXTENSIONS,
        help="PDF, DOCX, PPTX, XLSX, Markdown oder TXT",
    )

    _run_detection(uploaded, choices)

    sug: MetadataSuggestion | None = st.session_state.get("_meta_suggestion")
    v = st.session_state.get("_form_version", 0)

    if sug:
        st.info(
            "Metadaten automatisch vorausgefüllt — "
            "bitte prüfen und ggf. anpassen."
        )

    # ── Sorte ──
    sorte_index = _find_index(sorten, sug.sorte if sug else None) or 0
    sorte = st.selectbox(
        "Sorte (Zielverzeichnis)",
        options=sorten, index=sorte_index, key=f"sorte_{v}",
    )

    # ── Metadaten ──
    st.subheader("Metadaten")
    col1, col2 = st.columns(2)

    dt_opts = sorted(choices["doc_type"])
    be_opts = sorted(choices["bereich"])
    hk_opts = sorted(choices["herkunft"])
    qt_opts = sorted(choices["quelltyp"])
    vt_opts = sorted(choices["vertraulichkeit"])
    st_opts = sorted(choices["status"])

    with col1:
        titel = st.text_input(
            "Titel*", value=sug.titel if sug else "", key=f"titel_{v}",
        )
        doc_type = st.selectbox(
            "Dokumenttyp*", options=dt_opts,
            format_func=lambda s: choices["doc_type"][s],
            index=_find_index(dt_opts, sug.doc_type if sug else None),
            placeholder="— Bitte wählen —", key=f"doc_type_{v}",
        )
        bereich = st.multiselect(
            "Bereich* (mind. 1)", options=be_opts,
            format_func=lambda s: choices["bereich"][s],
            default=[
                b for b in (sug.bereich if sug else []) if b in be_opts
            ],
            key=f"bereich_{v}",
        )
        herkunft = st.selectbox(
            "Herkunft*", options=hk_opts,
            format_func=lambda s: choices["herkunft"][s],
            index=_find_index(hk_opts, sug.herkunft if sug else None),
            placeholder="— Bitte wählen —", key=f"herkunft_{v}",
        )
        quelltyp = st.selectbox(
            "Quelltyp*", options=qt_opts,
            format_func=lambda s: choices["quelltyp"][s],
            index=_find_index(qt_opts, sug.quelltyp if sug else None),
            placeholder="— Bitte wählen —", key=f"quelltyp_{v}",
        )

    with col2:
        vertraulichkeit = st.selectbox(
            "Vertraulichkeit* (bewusst wählen!)", options=vt_opts,
            format_func=lambda s: choices["vertraulichkeit"][s],
            index=_find_index(
                vt_opts, sug.vertraulichkeit if sug else None
            ),
            placeholder="— Bitte wählen —", key=f"vertraulichkeit_{v}",
        )
        status = st.selectbox(
            "Status", options=st_opts,
            format_func=lambda s: choices["status"][s],
            index=_find_index(
                st_opts, sug.status if sug else None
            ) or 0,
            key=f"status_{v}",
        )
        jahr = st.number_input(
            "Jahr", min_value=1990, max_value=2099,
            value=sug.jahr if sug and sug.jahr else 2025,
            step=1, key=f"jahr_{v}",
        )
        grad = None
        if doc_type == "abschlussarbeit":
            gr_opts = sorted(choices["grad"])
            grad = st.selectbox(
                "Grad", options=gr_opts,
                format_func=lambda s: choices["grad"][s],
                index=_find_index(
                    gr_opts, sug.grad if sug else None
                ),
                placeholder="— Bitte wählen —", key=f"grad_{v}",
            )

    # ── Facetten (Registry) ──
    st.subheader("Facetten (optional)")
    col3, col4 = st.columns(2)

    with col3:
        th_opts = sorted(choices["thema"])
        thema = st.multiselect(
            "Thema", options=th_opts,
            format_func=lambda s: f"{s} — {choices['thema'][s]}",
            default=[
                t for t in (sug.thema if sug else []) if t in th_opts
            ],
            key=f"thema_{v}",
        )
        an_opts = sorted(choices["anlage"])
        anlage = st.multiselect(
            "Anlage", options=an_opts,
            format_func=lambda s: f"{s} — {choices['anlage'][s]}",
            default=[
                a for a in (sug.anlage if sug else []) if a in an_opts
            ],
            key=f"anlage_{v}",
        )

    with col4:
        pr_opts = sorted(choices["projekt"])
        projekt = st.multiselect(
            "Projekt", options=pr_opts,
            format_func=lambda s: f"{s} — {choices['projekt'][s]}",
            default=[
                p for p in (sug.projekt if sug else []) if p in pr_opts
            ],
            key=f"projekt_{v}",
        )
        ap_opts = sorted(choices["ansprechperson"])
        ansprechperson = st.multiselect(
            "Ansprechperson", options=ap_opts,
            format_func=lambda s: f"{s} — {choices['ansprechperson'][s]}",
            default=[
                a for a in (sug.ansprechperson if sug else [])
                if a in ap_opts
            ],
            key=f"ansprechperson_{v}",
        )

    # ── Neuen Facetten-Wert anlegen ──
    with st.expander("Neuen Facetten-Wert anlegen"):
        render_vokabular_form()

    # ── Speichern ──
    st.divider()
    if st.button("Dokument speichern", type="primary"):
        handle_save(
            uploaded=uploaded,
            sorte=sorte,
            titel=titel,
            doc_type=doc_type,
            bereich=bereich,
            herkunft=herkunft,
            quelltyp=quelltyp,
            vertraulichkeit=vertraulichkeit,
            status=status,
            jahr=jahr,
            grad=grad,
            thema=thema,
            anlage=anlage,
            projekt=projekt,
            ansprechperson=ansprechperson,
        )


if __name__ == "__main__":
    main()
