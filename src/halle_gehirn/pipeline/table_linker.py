"""Table-to-Chunk-Verknuepfung.

Ordnet Tabellen-Chunks den passenden Body-Chunks zu: Extrahiert die
Tabellennummer aus der Caption, findet den Body-Chunk der die Tabelle
per Verweis (``Tabelle 3``, ``Tab. 3``, ``Table 3``) einfuehrt, und
haengt den referenzierenden Absatz als ``table_context`` an den
Tabellen-Chunk. Dieser Kontext wird mit-embedded (analog zu
``context_prefix``), damit Tabellen-Chunks bei semantischer Suche
den interpretierenden Text tragen.
"""
from __future__ import annotations

import re

import structlog

from halle_gehirn.pipeline.chunker import Chunk

logger = structlog.get_logger(__name__)

# "Tabelle 3", "Tab. 3", "Table 3", "Tafel 2"
_TABLE_NUM_RE = re.compile(
    r"(?:Tabelle|Tab\.?|Table|Tafel)\s+(\d+)",
    re.IGNORECASE,
)


def extract_table_number(caption: str | None) -> int | None:
    """Extrahiert die Tabellennummer aus einer Caption.

    Args:
        caption: Caption-Text (z.B. "Tabelle 3: Messergebnisse").

    Returns:
        Die Nummer als int oder None.
    """
    if not caption:
        return None
    match = _TABLE_NUM_RE.search(caption)
    return int(match.group(1)) if match else None


def find_table_refs_in_text(text: str) -> set[int]:
    """Findet alle Tabellennummern-Referenzen im Text.

    Args:
        text: Chunk-Text.

    Returns:
        Menge der referenzierten Tabellennummern.
    """
    return {int(m.group(1)) for m in _TABLE_NUM_RE.finditer(text)}


def link_tables_to_chunks(
    chunks: list[Chunk],
    table_captions: list[str | None],
) -> None:
    """Verknuepft Tabellen-Chunks mit ihrem interpretierenden Body-Text.

    Regeln:
    1. Caption-Nummer extrahieren (``Tabelle N``).
    2. Body-Chunk finden, der ``Tabelle N`` im Text referenziert.
    3. Den referenzierenden Absatz (max. 300 Zeichen) als
       ``table_context`` an den Tabellen-Chunk haengen.

    Args:
        chunks: Liste von Chunks (wird in-place modifiziert).
        table_captions: Captions der Tabellen-Chunks in der Reihenfolge,
            in der sie im chunks-Array erscheinen (nur is_table Chunks).
    """
    if not table_captions:
        return

    table_chunks = [c for c in chunks if c.is_table]
    body_chunks = [c for c in chunks if not c.is_table]

    if len(table_chunks) != len(table_captions):
        logger.warning(
            "table_linker_mismatch",
            table_chunks=len(table_chunks),
            captions=len(table_captions),
        )
        return

    linked = 0
    for tc, caption in zip(table_chunks, table_captions, strict=True):
        tc.table_caption = caption
        tab_num = extract_table_number(caption)
        if tab_num is None:
            continue
        # Besten Body-Chunk finden (laengste Referenz-Passage)
        best_chunk: Chunk | None = None
        best_len = 0
        for bc in body_chunks:
            if tab_num in find_table_refs_in_text(bc.text) and len(bc.text) > best_len:
                best_chunk = bc
                best_len = len(bc.text)
        if best_chunk is not None:
            # Kuerzen auf max. 300 Zeichen
            context = best_chunk.text[:300]
            if len(best_chunk.text) > 300:
                context = context.rsplit(" ", 1)[0] + "..."
            tc.table_context = context
            linked += 1

    if linked:
        logger.info(
            "tables_linked",
            total_tables=len(table_chunks),
            linked=linked,
        )
