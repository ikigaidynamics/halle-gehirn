"""Streamlit-Demo-UI -- Phase 6.

Minimaler Chat-Client gegen /chat/stream.
Zeigt gestreamte Antwort, klickbare Quellen und Konfidenz-Ampel.

Starten: ``streamlit run src/halle_gehirn/ui/streamlit_app.py``
"""
from __future__ import annotations

import json
import uuid

import httpx
import streamlit as st

API_URL = "http://localhost:8000"

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
    st.set_page_config(page_title="Jarvis -- Halle-Gehirn")
    st.title("Jarvis -- Halle-Gehirn")
    st.caption(
        "KI-Assistent des Lehrstuhls fuer "
        "KI-gestuetzte Automatisierungstechnik"
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
        with httpx.stream(
            "POST",
            f"{API_URL}/chat/stream",
            json={
                "query": query,
                "session_id": st.session_state.session_id,
            },
            timeout=120.0,
        ) as response:
            for line in response.iter_lines():
                if not line.startswith("data: "):
                    continue
                data = json.loads(line[6:])

                if data["type"] == "token":
                    full_answer += data["content"]
                    placeholder.markdown(full_answer + "...")
                elif data["type"] == "done":
                    confidence = data.get("confidence", "")
                    sources = data.get("sources", [])

        placeholder.markdown(full_answer)
    except httpx.HTTPError as exc:
        placeholder.error(f"Verbindungsfehler: {exc}")

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
    """Zeigt klickbare Quellen an."""
    if not sources:
        return
    with st.expander("Quellen", expanded=False):
        for src in sources:
            titel = src.get("titel", "Unbekannt")
            url = src.get("url")
            snippet = (src.get("snippet", "") or "")[:150]
            score = src.get("score", 0)

            if url:
                st.markdown(f"**[{titel}]({url})** (Score: {score})")
            else:
                st.markdown(f"**{titel}** (Score: {score})")
            if snippet:
                st.caption(snippet)


if __name__ == "__main__":
    main()
