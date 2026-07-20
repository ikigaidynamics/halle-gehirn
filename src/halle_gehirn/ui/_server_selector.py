"""Ollama-Server-Auswahl fuer die Sidebar der Ingest-App.

Zeigt die konfigurierten Ollama-URLs als Selectbox mit Health-Status
(online/offline). Die ausgewaehlte URL wird in ``st.session_state``
gespeichert und kann per ``get_active_ollama_url()`` abgefragt werden.
"""
from __future__ import annotations

import httpx
import streamlit as st

from halle_gehirn.config import get_settings
from halle_gehirn.ui._styles import (
    render_collection_card,
    render_local_hint,
    status_dot,
)


def render_ollama_sidebar() -> None:
    """Rendert die Ollama-Server-Auswahl in der Sidebar."""
    s = get_settings()
    urls = [u.strip() for u in s.ollama_urls.split(",") if u.strip()]
    if s.ollama_url not in urls:
        urls.insert(0, s.ollama_url)

    with st.sidebar:
        st.markdown(
            '<p style="font-family:\'JetBrains Mono\',monospace;'
            "font-size:10px;font-weight:600;letter-spacing:0.16em;"
            'text-transform:uppercase;color:#a09d95;">'
            "Ollama-Server</p>",
            unsafe_allow_html=True,
        )
        active = st.session_state.get("active_ollama_url", s.ollama_url)

        statuses: dict[str, bool] = {}
        for url in urls:
            try:
                httpx.get(f"{url}/api/tags", timeout=2.0)
                statuses[url] = True
            except Exception:
                statuses[url] = False

        # Render each server as a styled row
        for url in urls:
            is_online = statuses[url]
            is_active = url == active
            dot = status_dot(is_online)
            label = "online" if is_online else "offline"
            label_color = "#2f9e44" if is_online else "#a09d95"
            bg = "#ffffff" if is_active else "transparent"
            border = (
                "1px solid rgba(0,0,0,0.10)"
                if is_active
                else "1px solid transparent"
            )

            st.markdown(
                f'<div style="display:flex;align-items:center;gap:9px;'
                f"padding:9px 12px;border-radius:9px;background:{bg};"
                f'border:{border};margin-bottom:4px;cursor:pointer;">'
                f"{dot}"
                f'<span style="font-family:\'JetBrains Mono\',monospace;'
                f'font-size:12px;font-weight:500;color:#2a2a2a;">'
                f"{url}</span>"
                f'<span style="font-size:10.5px;color:{label_color};'
                f'margin-left:auto;">{label}</span>'
                f"</div>",
                unsafe_allow_html=True,
            )

        # Hidden selectbox for actual state management
        selected = st.selectbox(
            "Server",
            options=urls,
            index=urls.index(active) if active in urls else 0,
            format_func=lambda u: (
                f"{u} ({'online' if statuses.get(u) else 'offline'})"
            ),
            label_visibility="collapsed",
        )
        if selected != active:
            st.session_state["active_ollama_url"] = selected
            st.rerun()
        st.session_state["active_ollama_url"] = selected

        # ── Collection-Card ──
        st.markdown("")  # spacer
        st.markdown(
            '<p style="font-family:\'JetBrains Mono\',monospace;'
            "font-size:10px;font-weight:600;letter-spacing:0.16em;"
            'text-transform:uppercase;color:#a09d95;">'
            "Collection</p>",
            unsafe_allow_html=True,
        )
        _render_collection_info()

        # ── Lokal-first Hinweis ──
        render_local_hint()


def _render_collection_info() -> None:
    """Zeigt Collection-Stats aus Qdrant in der Sidebar."""
    s = get_settings()
    name = s.qdrant_collection
    embedding = s.embedding_model

    try:
        from halle_gehirn.vector_store.qdrant_client import (
            list_indexed_documents,
        )
        docs_list = list_indexed_documents()
        docs = len(docs_list)
        chunks = sum(d["chunk_count"] for d in docs_list)
    except Exception:
        docs = 0
        chunks = 0

    render_collection_card(name, docs, chunks, embedding)


def get_active_ollama_url() -> str:
    """Liefert die aktuell ausgewaehlte Ollama-URL.

    Fallback: ``ollama_url`` aus den Settings.
    """
    return st.session_state.get(
        "active_ollama_url", get_settings().ollama_url,
    )
