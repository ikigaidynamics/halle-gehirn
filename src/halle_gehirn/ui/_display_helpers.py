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
# Literatur-Referenzen in eckigen Klammern:
# [12], [1, 3], [1-5], [9, p. 1], [1, pp. 1-5], [vgl. 3, S. 42]
_BRACKET_REF_RE = re.compile(
    r"\s*\["
    r"(?:vgl\.?\s*)?"
    r"\d+(?:[,\s\-\u2013]+\d+)*"
    r"(?:[,;]\s*(?:pp?\.?|S\.?|Kap\.?)\s*\d+(?:\s*[-\u2013]\s*\d+)?)?"
    r"\]",
    re.IGNORECASE,
)
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


# Markdown-Tabellen-Separator: |---|---|
_TABLE_SEP_RE = re.compile(
    r"^\s*\|?[\s:]*-{3,}[\s:]*(\|[\s:]*-{3,}[\s:]*)+\|?\s*$",
)


def md_table_to_html(text: str) -> str:
    """Konvertiert Markdown-Pipe-Tabellen in HTML-Tabellen.

    Erkennt Bloecke mit Pipe-Trennzeichen und einer Separator-Zeile
    und wandelt sie in ``<table>``-HTML um. Text ausserhalb von
    Tabellen bleibt unveraendert.

    Args:
        text: Bereits HTML-escapeter Text mit Markdown-Tabellen.

    Returns:
        Text mit HTML-Tabellen statt Markdown-Pipe-Tabellen.
    """
    if "|" not in text:
        return text
    lines = text.split("\n")
    result: list[str] = []
    i = 0
    while i < len(lines):
        if (
            i + 1 < len(lines)
            and _TABLE_SEP_RE.match(lines[i + 1])
            and "|" in lines[i]
        ):
            table_html, i = _parse_md_table(lines, i)
            result.append(table_html)
        else:
            result.append(lines[i])
            i += 1
    return "\n".join(result)


def _parse_md_table(
    lines: list[str], start: int,
) -> tuple[str, int]:
    """Parst einen Markdown-Tabellen-Block ab *start*.

    Returns:
        Tuple (HTML-String, naechster Index nach der Tabelle).
    """
    header_cells = _split_pipe_row(lines[start])
    thead = "<tr>" + "".join(
        f'<th style="padding:4px 8px; background:#f0f0f0;'
        f' border:1px solid #ddd; font-weight:600;">{c}</th>'
        for c in header_cells
    ) + "</tr>"
    i = start + 2  # Separator ueberspringen
    rows_html: list[str] = []
    while i < len(lines) and "|" in lines[i]:
        cells = _split_pipe_row(lines[i])
        row = "<tr>" + "".join(
            f'<td style="padding:4px 8px; border:1px solid #ddd;">'
            f"{c}</td>"
            for c in cells
        ) + "</tr>"
        rows_html.append(row)
        i += 1
    return (
        '<table style="border-collapse:collapse; width:100%;'
        ' margin:8px 0; font-size:0.88em;">'
        f"<thead>{thead}</thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table>"
    ), i


def _split_pipe_row(line: str) -> list[str]:
    """Splittet eine Pipe-getrennte Zeile in Zellen."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip() for cell in line.split("|")]


def render_meta_table(items: list[dict[str, str]]) -> None:
    """Rendert Metadaten als kompakte HTML-Tabelle in Streamlit."""
    rows_html = ""
    for item in items:
        key = html_mod.escape(item["Feld"])
        val = html_mod.escape(item["Wert"])
        rows_html += (
            f"<tr>"
            f'<td class="jv-meta-label">{key}</td>'
            f'<td class="jv-meta-value">{val}</td>'
            f"</tr>"
        )
    st.markdown(
        f'<table class="jv-meta-table">{rows_html}</table>',
        unsafe_allow_html=True,
    )
