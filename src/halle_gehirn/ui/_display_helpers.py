"""Hilfsfunktionen fuer die Darstellung von Chunk-Text in der UI.

Bereinigt rohen Markdown-Text fuer saubere Snippet-Anzeige
in streamlit_app.py und _dokument_tab.py.
"""
from __future__ import annotations

import html as html_mod
import re

import streamlit as st

# Abbildung/Tabelle-Referenzzeilen (deutsch)
_FIGURE_RE = re.compile(
    r"^\s*(Abbildung|Tabelle|Abb\.|Tab\.)\s+\d+[^:\n]*:.*$",
    re.MULTILINE,
)
# Literatur-Referenzen in eckigen Klammern: [12], [1, 3], [1-5]
_BRACKET_REF_RE = re.compile(r"\s*\[\d+(?:[,\s\-\u2013]+\d+)*\]")
# Isolierte Fussnoten-Ziffern am Zeilenende (1-3 Stellen, nach Whitespace)
_FOOTNOTE_RE = re.compile(r"(?<=\s)\d{1,3}\s*$", re.MULTILINE)
# Markdown-Heading-Marker (#### Text → Text)
_HEADING_RE = re.compile(r"^(#{1,6})\s+", re.MULTILINE)
# Bold/Italic-Marker (**text** oder *text*)
_BOLD_ITALIC_RE = re.compile(r"\*{1,3}([^*]+)\*{1,3}")
# Roemische Seitenzahlen alleinstehend (z.B. XXXV am Ende)
_ROMAN_PAGE_RE = re.compile(
    r"^\s*[IVXLCDM]{2,}\s*$", re.MULTILINE,
)
# "Datum: Unterschrift:" Zeilen
_SIGNATURE_RE = re.compile(
    r"^\s*Datum:\s*Unterschrift:\s*$", re.MULTILINE,
)
# Mehr als zwei aufeinanderfolgende Leerzeilen
_BLANK_LINES_RE = re.compile(r"\n{3,}")
# Abschnitts-Ueberschriften: nummerierte Zeilen wie "2.3.1 Grundlagen..."
_SECTION_HEADING_RE = re.compile(
    r"^\s*\d+(\.\d+)*\.?\s+[^\n]+$", re.MULTILINE,
)
# Markdown-Italic-Ueberschriften: _N.N.N Text_ (alleinstehende Zeile)
_ITALIC_HEADING_RE = re.compile(
    r"^\s*_\d+(\.\d+)*\.?\s+[^_\n]+_\s*$", re.MULTILINE,
)
# Listen-Erkennung (auf bereits HTML-escaptem Text)
_UL_ITEM_RE = re.compile(r"^(\s*)[-*]\s+(.+)$")
_OL_ITEM_RE = re.compile(r"^(\s*)\d+\.\s+(.+)$")


def clean_snippet(
    text: str, *, strip_headings: bool = False,
) -> str:
    """Bereinigt rohen Chunk-Text fuer die UI-Anzeige.

    Entfernt Markdown-Syntaxzeichen, Abbildungsreferenzen,
    Literaturverweise in eckigen Klammern, Boilerplate-Bloecke
    (Erklaerungen) und isolierte Fussnoten-Ziffern.

    Args:
        text: Roher Chunk-Text (evtl. mit Markdown-Artefakten).
        strip_headings: Abschnitts-Ueberschriften entfernen
            (fuer Chat-Snippets, wo der Breadcrumb die Heading-Info
            bereits enthaelt).

    Returns:
        Bereinigter Fliesstext.
    """
    if not text:
        return text
    result = text
    result = _FIGURE_RE.sub("", result)
    result = _HEADING_RE.sub("", result)
    result = _BOLD_ITALIC_RE.sub(r"\1", result)
    result = _BRACKET_REF_RE.sub("", result)
    result = _FOOTNOTE_RE.sub("", result)
    result = _ROMAN_PAGE_RE.sub("", result)
    result = _SIGNATURE_RE.sub("", result)
    if strip_headings:
        result = _ITALIC_HEADING_RE.sub("", result)
        result = _SECTION_HEADING_RE.sub("", result)
    result = _BLANK_LINES_RE.sub("\n\n", result)
    return result.strip()


def _collect_list_items(
    lines: list[str], start: int, pattern: re.Pattern[str],
) -> tuple[list[str], int]:
    """Sammelt aufeinanderfolgende Listeneintraege.

    Args:
        lines: Alle Zeilen des Textes.
        start: Startindex der ersten Listen-Zeile.
        pattern: Regex mit Capture-Group 2 = Item-Text.

    Returns:
        Tuple aus (Item-Texte, naechster Index nach der Liste).
    """
    items: list[str] = []
    i = start
    while i < len(lines):
        m = pattern.match(lines[i])
        if not m:
            break
        items.append(m.group(2))
        i += 1
    return items, i


def md_lists_to_html(escaped_text: str) -> str:
    """Konvertiert Markdown-Listen in HTML (auf bereits escaptem Text).

    Erkennt ungeordnete (``-`` / ``*``) und geordnete (``1.`` / ``2.``)
    Listen und wandelt sie in ``<ul>``/``<ol>``-HTML um.

    Args:
        escaped_text: HTML-escapeter Text.

    Returns:
        Text mit HTML-Listen statt Markdown-Listen.
    """
    if not escaped_text:
        return escaped_text
    lines = escaped_text.split("\n")
    result: list[str] = []
    i = 0
    while i < len(lines):
        if _UL_ITEM_RE.match(lines[i]):
            items, i = _collect_list_items(lines, i, _UL_ITEM_RE)
            lis = "".join(f"<li>{item}</li>" for item in items)
            result.append(f"<ul style='margin:4px 0;padding-left:20px'>{lis}</ul>")
        elif _OL_ITEM_RE.match(lines[i]):
            items, i = _collect_list_items(lines, i, _OL_ITEM_RE)
            lis = "".join(f"<li>{item}</li>" for item in items)
            result.append(f"<ol style='margin:4px 0;padding-left:20px'>{lis}</ol>")
        else:
            result.append(lines[i])
            i += 1
    return "\n".join(result)


def render_meta_table(items: list[dict[str, str]]) -> None:
    """Rendert Metadaten als kompakte HTML-Tabelle in Streamlit."""
    rows_html = ""
    for item in items:
        key = html_mod.escape(item["Feld"])
        val = html_mod.escape(item["Wert"])
        rows_html += (
            f"<tr>"
            f'<td style="padding: 4px 8px; font-weight: 600; '
            f'background: #f0f0f0; border: 1px solid #ddd;">{key}</td>'
            f'<td style="padding: 4px 8px; border: 1px solid #ddd; '
            f'font-family: monospace; font-size: 0.85em;">{val}</td>'
            f"</tr>"
        )
    st.markdown(
        f'<table style="border-collapse: collapse; width: 100%; '
        f'margin-top: 4px;">{rows_html}</table>',
        unsafe_allow_html=True,
    )
