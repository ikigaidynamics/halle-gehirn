"""Streamlit-Demo-UI -- Phase 6.

Minimaler Chat-Client gegen /chat/stream.
Zeigt gestreamte Antwort, klickbare Quellen und Konfidenz-Ampel.

Starten: ``streamlit run src/halle_gehirn/ui/streamlit_app.py``
"""
from __future__ import annotations

import html
import json
import uuid
from pathlib import Path

import httpx
import streamlit as st

from halle_gehirn.config import get_settings
from halle_gehirn.ui._display_helpers import clean_snippet

_PUBLIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "public"

def _check_api_health(api_url: str) -> bool:
    """Prueft ob die API erreichbar ist (GET /health)."""
    try:
        resp = httpx.get(f"{api_url}/health", timeout=3.0)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


_COLORS: dict[str, str] = {
    "gruen": "#28a745",
    "gelb": "#ffc107",
    "rot": "#dc3545",
    "": "#6c757d",
}

_LABELS: dict[str, str] = {
    "gruen": "Hoch",
    "gelb": "Mittel",
    "rot": "Niedrig",
}


def main() -> None:
    """Hauptfunktion der Streamlit-App."""
    icon_path = _PUBLIC_DIR / "MD_Icon_bg.jpg"
    st.set_page_config(
        page_title="Jarvis — KI-Assistent",
        page_icon=str(icon_path) if icon_path.exists() else None,
        layout="centered",
    )

    # ── MDZ-Branding: Custom CSS + Header ──
    st.markdown(
        """<style>
        .stApp [data-testid="stHeader"] { background: transparent; }
        .stChatInput textarea { border-color: #c41230 !important; }
        .stChatInput textarea:focus { border-color: #c41230 !important;
            box-shadow: 0 0 0 1px #c41230 !important; }
        div[data-testid="stChatMessage"] .stMarkdown a { color: #c41230; }
        </style>""",
        unsafe_allow_html=True,
    )

    # Logo-Header
    logo_path = _PUBLIC_DIR / "MD_zentrum_Spreeland.png"
    if logo_path.exists():
        _col_l, col_logo, _col_r = st.columns([1, 2, 1])
        with col_logo:
            st.image(str(logo_path), width="stretch")

    st.markdown(
        '<h1 style="text-align: center; margin-bottom: 0;">'
        "Jarvis</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p style="text-align: center; color: #666; margin-top: 0;">'
        "KI-Assistent · Mittelstand-Digital Zentrum Spreeland · "
        "BTU Cottbus-Senftenberg</p>",
        unsafe_allow_html=True,
    )

    # Foerderhinweis in Sidebar
    with st.sidebar:
        foerder_path = _PUBLIC_DIR / "Mittellstand-Digital@BMWK.png"
        if foerder_path.exists():
            st.image(str(foerder_path), width="stretch")
        st.caption(
            "Gefördert durch das Bundesministerium für Wirtschaft "
            "und Klimaschutz"
        )

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "session_id" not in st.session_state:
        st.session_state.session_id = uuid.uuid4().hex[:8]

    # Chat-History anzeigen
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("confidence"):
                _render_confidence(msg["confidence"])
            if msg.get("sources"):
                _render_sources(msg["sources"])

    # API-Status pruefen
    api_url = get_settings().api_base_url
    api_ok = _check_api_health(api_url)

    if not api_ok:
        st.warning(
            f"API nicht erreichbar unter **{api_url}**.\n\n"
            "Bitte sicherstellen, dass:\n"
            "1. Docker läuft (Qdrant + Ollama)\n"
            "2. Die FastAPI-App gestartet ist: "
            "`uvicorn halle_gehirn.api.main:app "
            f"--host 0.0.0.0 --port {get_settings().api_port}`\n\n"
            "Konfiguration: `API_PORT` / `API_BASE_URL` in `.env`"
        )

    # User-Input
    if prompt := st.chat_input("Frage an Jarvis..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            answer, confidence, sources = _stream_response(prompt)
            if confidence:
                _render_confidence(confidence)
            if sources:
                _render_sources(sources)

        st.session_state.messages.append({
            "role": "assistant",
            "content": answer,
            "confidence": confidence,
            "sources": sources,
        })


def _stream_response(
    query: str,
) -> tuple[str, str, list[dict[str, str]]]:
    """Streamt die Antwort von /chat/stream.

    Args:
        query: Die Benutzeranfrage.

    Returns:
        Tuple (answer, confidence, sources).
    """
    placeholder = st.empty()
    full_answer = ""
    confidence = ""
    sources: list[dict[str, str]] = []

    try:
        # Connect-Timeout kurz, Read-Timeout lang: waehrend qwen3
        # den <think>-Block generiert und beim Grounding-Check nach
        # der Generierung fliessen keine SSE-Events.
        stream_timeout = httpx.Timeout(
            connect=10.0, read=300.0, write=10.0, pool=10.0,
        )
        with httpx.stream(
            "POST",
            f"{get_settings().api_base_url}/chat/stream",
            json={
                "query": query,
                "session_id": st.session_state.session_id,
            },
            timeout=stream_timeout,
        ) as response:
            for line in response.iter_lines():
                if not line.startswith("data: "):
                    continue
                data = json.loads(line[6:])

                if data["type"] == "token":
                    full_answer += data["content"]
                    placeholder.markdown(full_answer + "...")
                elif data["type"] == "status":
                    # Keepalive — Verbindung halten, nichts anzeigen
                    pass
                elif data["type"] == "done":
                    confidence = data.get("confidence", "")
                    sources = data.get("sources", [])

        placeholder.markdown(full_answer)
    except httpx.ConnectError:
        api_url = get_settings().api_base_url
        placeholder.error(
            f"Keine Verbindung zur API ({api_url}/chat/stream). "
            "Läuft die FastAPI-App? → "
            f"`uvicorn halle_gehirn.api.main:app "
            f"--port {get_settings().api_port}`"
        )
    except httpx.HTTPError as exc:
        placeholder.error(f"API-Fehler: {exc}")

    return full_answer, confidence, sources


def _render_confidence(confidence: str) -> None:
    """Zeigt die Konfidenz-Ampel an."""
    if not confidence:
        return
    color = _COLORS.get(confidence, _COLORS[""])
    label = _LABELS.get(confidence, confidence)
    st.markdown(
        f'<span style="color:{color}; font-weight:bold;">'
        f"Konfidenz: {label}</span>",
        unsafe_allow_html=True,
    )


def _render_sources(sources: list[dict[str, str]]) -> None:
    """Zeigt Quellen mit Dateipfad und Snippet an."""
    if not sources:
        return
    with st.expander("Quellen", expanded=False):
        for src in sources:
            titel = src.get("titel", "Unbekannt")
            url = src.get("url")
            datei = src.get("datei", "")
            snippet = src.get("snippet", "")
            score = src.get("score", 0)
            breadcrumb = src.get("breadcrumb", "")
            page = src.get("page")

            # Titel + Score
            header = f"**[{titel}]({url})**" if url else f"**{titel}**"
            header += f" (Score: {score})"
            st.markdown(header)

            # Datei-Info
            info_parts: list[str] = []
            if datei:
                info_parts.append(f"`data/manual/{datei}`")
            if page:
                info_parts.append(f"Seite {page}")
            if breadcrumb:
                info_parts.append(breadcrumb)
            if info_parts:
                st.caption(" · ".join(info_parts))

            # Snippet (bereinigt, Fliesstext ohne Ueberschriften)
            if snippet:
                cleaned = clean_snippet(snippet, strip_headings=True)
                escaped = html.escape(cleaned)
                st.markdown(
                    f'<div style="white-space: pre-wrap; font-size: 0.9em;'
                    f" color: #555; background: #f8f9fa; padding: 10px;"
                    f' border-radius: 6px; border-left: 3px solid #c41230;'
                    f' max-height: 400px; overflow-y: auto;">'
                    f"{escaped}</div>",
                    unsafe_allow_html=True,
                )
            st.divider()



if __name__ == "__main__":
    main()
