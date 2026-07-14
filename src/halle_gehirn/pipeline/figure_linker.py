"""Figure-to-Chunk-Verknuepfung.

Ordnet extrahierte Abbildungen (FigureBlocks) den passenden Chunks zu.
Primaer ueber Caption-Nummern-Referenzen im Chunk-Text, Fallback ueber
Seitenzuordnung. Kein Chunk bleibt ohne Bild wenn ein Bild auf seiner
Seite liegt und keine Nummern-Referenz existiert.
"""
from __future__ import annotations

import re

import structlog

from halle_gehirn.extraction.base import FigureBlock
from halle_gehirn.pipeline.chunker import Chunk

logger = structlog.get_logger(__name__)

# Regex fuer "Abbildung 12", "Abb. 3", "Bild 7", "Figure 5", "Fig. 1"
_FIGURE_NUM_RE = re.compile(
    r"(?:Abbildung|Abb\.?|Bild|Figure|Fig\.?)\s+(\d+)",
    re.IGNORECASE,
)


def extract_figure_number(caption: str | None) -> int | None:
    """Extrahiert die Abbildungsnummer aus einer Caption.

    Args:
        caption: Caption-Text (z.B. "Abbildung 3: Systemarchitektur").

    Returns:
        Die Nummer als int oder None.
    """
    if not caption:
        return None
    match = _FIGURE_NUM_RE.search(caption)
    return int(match.group(1)) if match else None


def find_figure_refs_in_text(text: str) -> set[int]:
    """Findet alle Abbildungsnummern-Referenzen im Text.

    Args:
        text: Chunk-Text.

    Returns:
        Menge der referenzierten Abbildungsnummern.
    """
    return {int(m.group(1)) for m in _FIGURE_NUM_RE.finditer(text)}


def link_figures_to_chunks(
    chunks: list[Chunk],
    figures: list[FigureBlock],
) -> None:
    """Verknuepft Figures mit Chunks (in-place).

    Regeln (in dieser Reihenfolge):
    1. PRIMAER: Caption-Nummer extrahieren, Figur an jeden Chunk haengen
       dessen Text die gleiche Nummer referenziert.
    2. FALLBACK: Figuren ohne Nummer ODER ohne Text-Match werden an
       Chunks mit gleicher Seite gehaengt.

    Args:
        chunks: Liste von Chunks (wird in-place modifiziert).
        figures: Liste von FigureBlocks.
    """
    if not figures:
        return

    linked_by_number = 0
    linked_by_page = 0

    for fig in figures:
        fig_num = extract_figure_number(fig.caption)
        matched = False

        # Primaer: Nummern-Referenz im Chunk-Text
        if fig_num is not None:
            for chunk in chunks:
                refs_in_text = find_figure_refs_in_text(chunk.text)
                if fig_num in refs_in_text:
                    _attach_figure(chunk, fig)
                    matched = True
                    linked_by_number += 1

        # Fallback: Seitenzuordnung
        if not matched and fig.page is not None:
            for chunk in chunks:
                if chunk.page == fig.page:
                    _attach_figure(chunk, fig)
                    matched = True
                    linked_by_page += 1

    logger.info(
        "figures_linked",
        total_figures=len(figures),
        linked_by_number=linked_by_number,
        linked_by_page=linked_by_page,
    )


def _attach_figure(chunk: Chunk, fig: FigureBlock) -> None:
    """Haengt eine Figur an einen Chunk (dedupliziert)."""
    if fig.image_path not in chunk.figure_refs:
        chunk.figure_refs.append(fig.image_path)
        if fig.caption:
            chunk.figure_captions.append(fig.caption)
