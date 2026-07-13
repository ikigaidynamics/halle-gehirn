"""Ollama-Server-Auswahl fuer die Sidebar der Ingest-App.

Zeigt die konfigurierten Ollama-URLs als Selectbox mit Health-Status
(online/offline). Die ausgewaehlte URL wird in ``st.session_state``
gespeichert und kann per ``get_active_ollama_url()`` abgefragt werden.
"""
from __future__ import annotations

import httpx
import streamlit as st

from halle_gehirn.config import get_settings


def render_ollama_sidebar() -> None:
    """Rendert die Ollama-Server-Auswahl in der Sidebar."""
    s = get_settings()
    urls = [u.strip() for u in s.ollama_urls.split(",") if u.strip()]
    if s.ollama_url not in urls:
        urls.insert(0, s.ollama_url)

    with st.sidebar:
        st.subheader("Ollama-Server")
        active = st.session_state.get("active_ollama_url", s.ollama_url)

        labels: dict[str, str] = {}
        for url in urls:
            try:
                httpx.get(f"{url}/api/tags", timeout=2.0)
                labels[url] = f"{url} (online)"
            except Exception:
                labels[url] = f"{url} (offline)"

        selected = st.selectbox(
            "Server",
            options=urls,
            index=urls.index(active) if active in urls else 0,
            format_func=lambda u: labels.get(u, u),
        )
        if selected != active:
            st.session_state["active_ollama_url"] = selected
            st.rerun()
        st.session_state["active_ollama_url"] = selected


def get_active_ollama_url() -> str:
    """Liefert die aktuell ausgewaehlte Ollama-URL.

    Fallback: ``ollama_url`` aus den Settings.
    """
    return st.session_state.get(
        "active_ollama_url", get_settings().ollama_url,
    )
