"""Sidebar-Facetten-Filter fuer die Chat-UI (WP6).

Rendert Multiselects fuer doc_type/bereich/anlage + Jahr-Eingabe und
baut daraus das ``filters``-Dict fuer die Chat-API (Qdrant-Payload-
Filter, siehe retriever/_build_filter: Listen → MatchAny, Skalar →
MatchValue). Facetten statt Ordner — die Taxonomie wird im Chat nutzbar.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st
import yaml

from halle_gehirn.vector_store.schema import Bereich, DocType

_VOKABULAR_PATH = Path("data/vokabular.yaml")

_DOC_TYPE_LABELS: dict[str, str] = {
    "abschlussarbeit": "Abschlussarbeit",
    "promotion": "Promotion",
    "projektbericht": "Projektbericht",
    "anlagendoku": "Anlagendoku",
    "handbuch": "Handbuch",
    "flyer": "Flyer",
    "online_beitrag": "Online-Beitrag",
    "workshop_slides": "Workshop-Folien",
    "lehrbuch": "Lehrbuch",
    "experten_transkript": "Experten-Transkript",
}


@st.cache_data(ttl=300)
def _load_anlage_options() -> dict[str, str]:
    """Laedt die anlage-Registry (Slug → Label) aus vokabular.yaml."""
    if not _VOKABULAR_PATH.exists():
        return {}
    raw = yaml.safe_load(_VOKABULAR_PATH.read_text(encoding="utf-8")) or {}
    anlage = raw.get("anlage") or {}
    return {str(slug): str(label) for slug, label in anlage.items()}


def render_filter_sidebar() -> dict[str, Any]:
    """Rendert die Facetten-Filter und liefert das filters-Dict.

    Returns:
        Dict fuer ``ChatRequest.filters`` — nur belegte Facetten;
        leer, wenn keine Filter aktiv sind.
    """
    filters: dict[str, Any] = {}
    with st.sidebar:
        st.subheader("Filter")
        doc_types = st.multiselect(
            "Dokumenttyp",
            options=[d.value for d in DocType],
            format_func=lambda v: _DOC_TYPE_LABELS.get(v, v),
        )
        bereiche = st.multiselect(
            "Bereich",
            options=[b.value for b in Bereich],
            format_func=str.capitalize,
        )
        anlage_options = _load_anlage_options()
        anlagen = st.multiselect(
            "Anlage",
            options=list(anlage_options.keys()),
            format_func=lambda v: anlage_options.get(v, v),
        )
        jahr_text = st.text_input("Jahr", placeholder="z.B. 2025")

        if doc_types:
            filters["doc_type"] = doc_types
        if bereiche:
            filters["bereich"] = bereiche
        if anlagen:
            filters["anlage"] = anlagen
        if jahr_text.strip():
            if jahr_text.strip().isdigit():
                filters["jahr"] = int(jahr_text.strip())
            else:
                st.caption("⚠ Jahr muss eine Zahl sein — ignoriert")

        if filters:
            st.caption(f"Aktiv: {len(filters)} Filter")
    return filters
