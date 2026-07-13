"""Hilfsfunktionen fuer den 'Neues Dokument'-Tab der Ingest-App.

Ausgelagert aus ingest_app.py, um die Dateilaenge unter 300 Zeilen
zu halten. Enthaelt Speicher-Logik und Vokabular-Formular.
"""
from __future__ import annotations

from typing import Any

import streamlit as st

from halle_gehirn.manifest.editor import (
    save_manifest_entry,
    save_uploaded_file,
    save_vokabular_entry,
    validate_entry,
)
from halle_gehirn.pipeline.ingest import ManifestEntry

_FACETTEN_LABELS: dict[str, str] = {
    "thema": "Thema (Forschungsschwerpunkt)",
    "anlage": "Anlage (Hallengerät)",
    "projekt": "Projekt",
    "ansprechperson": "Ansprechperson",
}


def render_vokabular_form() -> None:
    """Mini-Formular zum Anlegen neuer Facetten-Werte in vokabular.yaml."""
    st.caption(
        "Hier können neue Werte für die wachsenden Facetten "
        "(Thema, Anlage, Projekt, Ansprechperson) angelegt werden."
    )
    vc1, vc2 = st.columns(2)
    with vc1:
        facet = st.selectbox(
            "Facette",
            options=list(_FACETTEN_LABELS),
            format_func=lambda f: _FACETTEN_LABELS[f],
        )
        new_slug = st.text_input(
            "Slug (snake_case)",
            help="z. B. neuer_roboter — nur Kleinbuchstaben, Ziffern, Unterstrich",
        )
    with vc2:
        new_label = st.text_input(
            "Anzeigename",
            help="z. B. Neuer Roboter XY-500",
        )

    if st.button("Facetten-Wert speichern"):
        if not new_slug or not new_label:
            st.error("Slug und Anzeigename sind Pflichtfelder.")
            return
        try:
            save_vokabular_entry(facet, new_slug.strip(), new_label.strip())
            st.toast(
                f"Gespeichert: {facet} → "
                f"{new_slug.strip()} = {new_label.strip()}",
                icon="✅",
            )
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def handle_save(
    *,
    uploaded: Any,
    sorte: str,
    titel: str,
    doc_type: str | None,
    bereich: list[str],
    herkunft: str | None,
    quelltyp: str | None,
    vertraulichkeit: str | None,
    status: str | None,
    jahr: int,
    grad: str | None,
    thema: list[str],
    anlage: list[str],
    projekt: list[str],
    ansprechperson: list[str],
) -> None:
    """Validiert und speichert einen neuen Manifest-Eintrag."""
    if uploaded is None:
        st.error("Bitte eine Datei hochladen.")
        return

    filename = uploaded.name  # type: ignore[union-attr]
    datei_rel = f"{sorte}/{filename}"

    entry = ManifestEntry(
        datei=datei_rel,
        titel=titel,
        doc_type=doc_type or "",
        bereich=bereich,
        herkunft=herkunft or "",
        quelltyp=quelltyp or "primaer",
        thema=thema,
        anlage=anlage,
        projekt=projekt,
        ansprechperson=ansprechperson,
        jahr=jahr,
        vertraulichkeit=vertraulichkeit or "",
        status=status or "final",
        grad=grad,
    )

    errors = validate_entry(entry)
    if errors:
        for err in errors:
            st.error(err)
        return

    try:
        file_data: bytes = uploaded.read()  # type: ignore[union-attr]
        save_uploaded_file(file_data, filename, sorte)
    except FileExistsError as exc:
        st.error(str(exc))
        return
    except ValueError as exc:
        st.error(str(exc))
        return

    save_manifest_entry(entry)
    st.success(
        f"Gespeichert: **{titel}** → `data/manual/{datei_rel}`"
    )
    st.info("Seite neu laden, um den Bestand-Tab zu aktualisieren.")
