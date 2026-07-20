"""Zentrales CSS fuer das MDZ-Branding der Streamlit-Apps.

Injiziert via ``st.markdown(unsafe_allow_html=True)`` als ``<style>``-Block.
Design-Tokens aus ``design_handoff_jarvis_wissensbestand/README.md``.
"""
from __future__ import annotations

import streamlit as st

# Selbst-gehostete Fonts (fontsource CDN-frei, DSGVO-konform).
# Streamlit laeuft lokal — @import auf Bunny-Fonts als Fallback
# (EU-basiert, DSGVO-konform, kein Google).
_FONT_IMPORT = """
@import url('https://fonts.bunny.net/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
"""

_CSS = """
<style>
""" + _FONT_IMPORT + """

/* ── Basis ── */
html, body, [class*="css"] {
    font-family: "Inter", system-ui, -apple-system, sans-serif !important;
    -webkit-font-smoothing: antialiased;
}

/* ── Streamlit Topbar ausblenden (eigener Header) ── */
header[data-testid="stHeader"] {
    display: none !important;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: #faf9f6 !important;
    border-right: 1px solid rgba(0,0,0,0.07) !important;
}
section[data-testid="stSidebar"] .stMarkdown h3,
section[data-testid="stSidebar"] .stMarkdown h2 {
    font-family: "JetBrains Mono", monospace !important;
    font-size: 10px !important;
    font-weight: 600 !important;
    letter-spacing: 0.16em !important;
    text-transform: uppercase !important;
    color: #a09d95 !important;
}

/* ── Tab-Leiste ── */
button[data-baseweb="tab"] {
    font-family: "Inter", system-ui, sans-serif !important;
    font-size: 13.5px !important;
    font-weight: 600 !important;
    color: #6b6963 !important;
    padding: 15px 16px 13px !important;
    border-bottom: 2px solid transparent !important;
    background: transparent !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #E2001A !important;
    border-bottom-color: #E2001A !important;
}
div[data-baseweb="tab-highlight"] {
    background-color: #E2001A !important;
}
div[data-baseweb="tab-border"] {
    background-color: rgba(0,0,0,0.08) !important;
}

/* ── Buttons ── */
button[kind="primary"],
.stButton > button[kind="primary"],
button[data-testid="stBaseButton-primary"] {
    background-color: #E2001A !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    box-shadow: 0 6px 18px -6px rgba(226,0,26,0.6) !important;
    padding: 11px 22px !important;
}
button[kind="primary"]:hover,
button[data-testid="stBaseButton-primary"]:hover {
    background-color: #b30015 !important;
}
button[kind="secondary"],
button[data-testid="stBaseButton-secondary"] {
    border: 1px solid rgba(0,0,0,0.12) !important;
    background: #fff !important;
    color: #8a877f !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 11.5px !important;
}

/* ── Inputs / Selectboxen ── */
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div,
.stTextInput > div > div,
.stSelectbox > div > div,
.stNumberInput > div > div {
    border-radius: 9px !important;
    border-color: rgba(0,0,0,0.12) !important;
}

/* ── Multiselect Chips ── */
span[data-baseweb="tag"] {
    background: rgba(226,0,26,0.1) !important;
    color: #E2001A !important;
    border-radius: 6px !important;
    font-size: 11px !important;
    font-weight: 500 !important;
}

/* ── Expander ── */
details[data-testid="stExpander"] {
    border-radius: 11px !important;
    border: 1px solid rgba(0,0,0,0.08) !important;
    background: #ffffff !important;
}
details[data-testid="stExpander"] summary {
    font-weight: 600 !important;
}

/* ── Metriken ── */
div[data-testid="stMetric"] {
    background: #ffffff !important;
    border: 1px solid rgba(0,0,0,0.08) !important;
    border-radius: 11px !important;
    padding: 13px !important;
    text-align: center !important;
}
div[data-testid="stMetric"] label {
    font-size: 10.5px !important;
    color: #8a877f !important;
}
div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    font-family: "JetBrains Mono", monospace !important;
    font-size: 22px !important;
    font-weight: 700 !important;
}

/* ── Dataframe / Tabelle ── */
div[data-testid="stDataFrame"] table {
    border-radius: 11px !important;
    overflow: hidden !important;
}
div[data-testid="stDataFrame"] th {
    background: #faf9f6 !important;
    font-family: "JetBrains Mono", monospace !important;
    font-size: 10px !important;
    font-weight: 600 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    color: #a09d95 !important;
}

/* ── Info/Warning/Success/Error Boxen ── */
div[data-testid="stAlert"] {
    border-radius: 9px !important;
}

/* ── Checkbox (Rot statt Standard) ── */
span[data-testid="stCheckbox"] label span[role="checkbox"][aria-checked="true"] {
    background-color: #E2001A !important;
    border-color: #E2001A !important;
}

/* ── File-Uploader ── */
section[data-testid="stFileUploader"] > div {
    border: 1.5px dashed rgba(226,0,26,0.3) !important;
    background: rgba(226,0,26,0.03) !important;
    border-radius: 12px !important;
}

/* ── Divider ── */
hr {
    border-color: rgba(0,0,0,0.08) !important;
}

/* ── Progress Bar ── */
div[data-testid="stProgress"] > div > div {
    background-color: #E2001A !important;
}
/* Progress-Text: nicht rot */
div[data-testid="stProgress"] p,
div[data-testid="stProgress"] span {
    color: #555 !important;
}
/* Caption-Text: neutral, nicht primary */
div[data-testid="stCaptionContainer"] p {
    color: #8a877f !important;
}
/* Spinner-Text: neutral */
div[data-testid="stStatusWidget"] span {
    color: #555 !important;
}
/* st.status: neutraler Header */
details[data-testid="stExpander"] summary span {
    color: #333 !important;
}

/* ── Monospace-Klasse (fuer Slugs, Dateinamen etc.) ── */
.jv-mono {
    font-family: "JetBrains Mono", monospace !important;
}

/* ── Status-Punkt (indexiert / nicht indexiert) ── */
.jv-dot-green {
    display: inline-block;
    width: 9px; height: 9px;
    border-radius: 50%;
    background: #2f9e44;
    box-shadow: 0 0 7px rgba(47,158,68,0.4);
}
.jv-dot-gray {
    display: inline-block;
    width: 9px; height: 9px;
    border-radius: 50%;
    background: #c9c6bf;
}

/* ── Chunk-Text-Box (roter linker Rand) ── */
.jv-chunk-text {
    padding: 11px 13px;
    border-radius: 8px;
    background: #f8f9fa;
    border-left: 3px solid #E2001A;
    font-size: 12.5px;
    line-height: 1.65;
    color: #333;
    white-space: pre-wrap;
    max-height: 400px;
    overflow-y: auto;
}

/* ── Context-Prefix-Box ── */
.jv-context-prefix {
    padding: 9px 12px;
    border-radius: 8px;
    background: #fff8e6;
    border: 1px solid rgba(227,160,8,0.3);
    font-size: 11.5px;
    line-height: 1.55;
    font-style: italic;
    color: #8a6d1a;
}

/* ── Meta-Tabelle (Chunk-Detail) ── */
.jv-meta-table {
    border-collapse: collapse;
    width: 100%;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid rgba(0,0,0,0.08);
}
.jv-meta-table td.jv-meta-label {
    padding: 5px 11px;
    font-size: 11px;
    font-weight: 600;
    background: #f3f2ef;
    color: #555;
    width: 120px;
}
.jv-meta-table td.jv-meta-value {
    padding: 5px 11px;
    font-family: "JetBrains Mono", monospace;
    font-size: 11px;
    color: #333;
}
.jv-meta-table tr + tr td {
    border-top: 1px solid rgba(0,0,0,0.05);
}

/* ── Collection-Card (Sidebar) ── */
.jv-collection-card {
    border-radius: 11px;
    border: 1px solid rgba(0,0,0,0.08);
    background: #ffffff;
    overflow: hidden;
}
.jv-collection-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 9px 12px;
}
.jv-collection-row + .jv-collection-row {
    border-top: 1px solid rgba(0,0,0,0.06);
}
.jv-collection-label {
    font-size: 12px;
    color: #8a877f;
}
.jv-collection-value {
    font-family: "JetBrains Mono", monospace;
    font-size: 12px;
    font-weight: 600;
    color: #2a2a2a;
}
.jv-collection-value-red {
    font-family: "JetBrains Mono", monospace;
    font-size: 11px;
    font-weight: 500;
    color: #E2001A;
}

/* ── Lokal-first Hinweis ── */
.jv-local-hint {
    padding: 12px;
    border-radius: 11px;
    background: rgba(226,0,26,0.04);
    border: 1px solid rgba(226,0,26,0.14);
    margin-top: 16px;
}
.jv-local-hint strong {
    font-size: 11.5px;
    font-weight: 600;
    color: #333;
}
.jv-local-hint p {
    font-size: 11px;
    line-height: 1.5;
    color: #7a776f;
    margin: 4px 0 0;
}

/* ── Log-Block (dunkel) ── */
.jv-log-block {
    border-radius: 10px;
    background: #1c1c1c;
    border: 1px solid rgba(0,0,0,0.2);
    padding: 13px 15px;
    font-family: "JetBrains Mono", monospace;
    font-size: 11px;
    line-height: 1.7;
    color: #c9c9c9;
    max-height: 300px;
    overflow-y: auto;
}
.jv-log-block .log-info { color: #7cd894; }
.jv-log-block .log-done { color: #e3b84a; }
.jv-log-block .log-error { color: #f0603a; }

/* ── Bestand-Karte (Dokument-Zeile) ── */
.jv-doc-card {
    display: flex;
    align-items: center;
    gap: 13px;
    padding: 13px 15px;
    border-radius: 11px;
    background: #ffffff;
    border: 1px solid rgba(0,0,0,0.08);
    margin-bottom: 8px;
}
.jv-doc-card .jv-doc-title {
    font-size: 13.5px;
    font-weight: 600;
    color: #1a1a1a;
}
.jv-doc-card .jv-doc-slug {
    font-family: "JetBrains Mono", monospace;
    font-size: 11px;
    font-weight: 400;
    color: #a09d95;
    margin-left: 6px;
}
.jv-doc-card .jv-doc-meta {
    font-size: 11.5px;
    color: #8a877f;
    margin-top: 3px;
}

/* ── Topbar (Custom) ── */
.jv-topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 22px;
    height: 64px;
    background: #ffffff;
    border-bottom: 1px solid rgba(0,0,0,0.08);
    margin: -1rem -1rem 1rem -1rem;
}
.jv-topbar-left {
    display: flex;
    align-items: center;
    gap: 12px;
}
.jv-topbar-left img {
    width: 36px;
    height: 36px;
    border-radius: 9px;
    object-fit: cover;
}
.jv-topbar-title {
    font-size: 16px;
    font-weight: 700;
    color: #1a1a1a;
    letter-spacing: -0.01em;
}
.jv-topbar-subtitle {
    font-size: 11.5px;
    color: #8a877f;
}
.jv-topbar-right {
    display: flex;
    align-items: center;
    gap: 10px;
}
.jv-badge-green {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 7px 11px;
    border-radius: 8px;
    background: rgba(47,158,68,0.08);
    border: 1px solid rgba(47,158,68,0.28);
}
.jv-badge-green .dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: #2f9e44;
    box-shadow: 0 0 8px rgba(47,158,68,0.5);
}
.jv-badge-green span.label {
    font-family: "JetBrains Mono", monospace;
    font-size: 11px;
    font-weight: 500;
    color: #2f9e44;
}
.jv-chip {
    padding: 7px 10px;
    border-radius: 8px;
    background: #f5f4f1;
    border: 1px solid rgba(0,0,0,0.08);
    font-size: 11px;
    font-weight: 600;
    color: #555;
}

/* ── Foerder-Fusszeile ── */
.jv-footer {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 14px 24px;
    background: #f3f2ef;
    border-top: 1px solid rgba(0,0,0,0.08);
    margin: 1rem -1rem -1rem -1rem;
}
.jv-footer img { height: 34px; width: auto; }
.jv-footer span {
    font-size: 11px;
    color: #777;
    line-height: 1.4;
}
</style>
"""


def inject_custom_css() -> None:
    """Injiziert das MDZ-Design-CSS in die Streamlit-App."""
    st.markdown(_CSS, unsafe_allow_html=True)


def render_topbar(logo_path: str) -> None:
    """Rendert die MDZ-Topbar mit Logo und Badges."""
    import base64
    from pathlib import Path

    logo_b64 = ""
    p = Path(logo_path)
    if p.exists():
        logo_b64 = base64.b64encode(p.read_bytes()).decode()

    img_tag = (
        f'<img src="data:image/jpeg;base64,{logo_b64}" />'
        if logo_b64
        else ""
    )

    st.markdown(
        f"""
        <div class="jv-topbar">
          <div class="jv-topbar-left">
            {img_tag}
            <div>
              <div class="jv-topbar-title">Jarvis — Wissensbestand</div>
              <div class="jv-topbar-subtitle">
                Dokumentenverwaltung &amp; Indexierung ·
                Mittelstand-Digital Zentrum Spreeland
              </div>
            </div>
          </div>
          <div class="jv-topbar-right">
            <div class="jv-badge-green">
              <span class="dot"></span>
              <span class="label">On-Prem</span>
            </div>
            <span class="jv-chip">DSGVO</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_footer(logo_path: str) -> None:
    """Rendert die Foerder-Fusszeile."""
    import base64
    from pathlib import Path

    logo_b64 = ""
    p = Path(logo_path)
    if p.exists():
        logo_b64 = base64.b64encode(p.read_bytes()).decode()

    img_tag = (
        f'<img src="data:image/png;base64,{logo_b64}" />'
        if logo_b64
        else ""
    )

    st.markdown(
        f"""
        <div class="jv-footer">
          {img_tag}
          <span>Ein Angebot des Mittelstand-Digital Zentrums Spreeland</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_collection_card(
    name: str, docs: int, chunks: int, embedding: str,
) -> None:
    """Rendert die Collection-Info-Karte in der Sidebar."""
    st.markdown(
        f"""
        <div class="jv-collection-card">
          <div class="jv-collection-row">
            <span class="jv-collection-label">Name</span>
            <span class="jv-collection-value-red">{name}</span>
          </div>
          <div class="jv-collection-row">
            <span class="jv-collection-label">Dokumente</span>
            <span class="jv-collection-value">{docs}</span>
          </div>
          <div class="jv-collection-row">
            <span class="jv-collection-label">Chunks</span>
            <span class="jv-collection-value">{chunks}</span>
          </div>
          <div class="jv-collection-row">
            <span class="jv-collection-label">Embedding</span>
            <span class="jv-collection-value" style="font-size:10.5px;
              font-weight:500;color:#555;">{embedding}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_local_hint() -> None:
    """Rendert den Lokal-first-Hinweis."""
    st.markdown(
        """
        <div class="jv-local-hint">
          <strong>Lokal-first</strong>
          <p>Extraktion, Embedding &amp; Vektor-DB laufen on-prem.
          Keine Cloud, DSGVO-konform.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_dot(indexed: bool) -> str:
    """Gibt HTML fuer einen Status-Punkt zurueck."""
    cls = "jv-dot-green" if indexed else "jv-dot-gray"
    return f'<span class="{cls}"></span>'
