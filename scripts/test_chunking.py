"""Chunking-Test auf vollstaendigem pymupdf4llm-Dokument.

Extrahiert die Abschlussarbeit (mit DOCLING_OCR=false -> Fallback),
chunked, filtert und gibt alle Chunks mit Token-Zahl + erste 80 Zeichen aus.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Projekt-Root / CWD auf halle-gehirn setzen
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root / "src"))
os.chdir(_project_root)

from halle_gehirn.extraction.docling_extractor import DoclingExtractor
from halle_gehirn.pipeline.chunk_filter import filter_chunks
from halle_gehirn.pipeline.chunker import MarkdownChunker, count_tokens

PDF_PATH = (
    _project_root
    / "data"
    / "manual"
    / "abschlussarbeiten"
    / "Abschlussarbeit_Zhili Wang.pdf"
)


def main() -> None:
    if not PDF_PATH.exists():
        print(f"FEHLER: PDF nicht gefunden: {PDF_PATH}")
        sys.exit(1)

    print(f"PDF: {PDF_PATH.name} ({PDF_PATH.stat().st_size / 1024:.0f} KB)")

    # --- 1. Extraktion ---
    print("\n=== EXTRAKTION ===")
    extractor = DoclingExtractor()
    doc = extractor.extract(PDF_PATH)
    print(f"  Backend:     {doc.meta.get('extraction_backend', 'docling')}")
    print(f"  Seiten:      {doc.page_count}")
    print(f"  MD-Zeichen:  {len(doc.body_md):,}")
    print(f"  MD-Tokens:   {count_tokens(doc.body_md):,}")
    print(f"  Tabellen:    {len(doc.tables)}")

    # --- 2. Heading-Analyse (pymupdf4llm-Format) ---
    print("\n=== HEADING-ANALYSE (pymupdf4llm-Format) ===")
    import re
    heading_re = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    headings = heading_re.findall(doc.body_md)
    print(f"  Headings gefunden: {len(headings)}")
    for i, (level, text) in enumerate(headings[:30]):
        print(f"    [{i:3d}] {level} {text[:70]}")
    if len(headings) > 30:
        print(f"    ... und {len(headings) - 30} weitere")

    # --- 3. Chunking ---
    print("\n=== CHUNKING (doc_type=abschlussarbeit) ===")
    chunker = MarkdownChunker()
    raw_chunks = chunker.chunk(doc, doc_type="abschlussarbeit")
    print(f"  Roh-Chunks:  {len(raw_chunks)}")

    # --- 4. Filterung ---
    print("\n=== FILTERUNG ===")
    filtered = filter_chunks(raw_chunks, doc_type="abschlussarbeit")
    print(f"  Nach Filter: {len(filtered)}")
    print(f"  Verworfen:   {len(raw_chunks) - len(filtered)}")

    # --- 5. Alle verbleibenden Chunks ---
    print(f"\n=== ALLE {len(filtered)} CHUNKS ===")
    print(f"{'Idx':>4} {'Tokens':>6} {'Chars':>7} {'Heading':>40}  Text (erste 80 Zeichen)")
    print("-" * 140)

    max_tokens = 0
    for chunk in filtered:
        tokens = count_tokens(chunk.text)
        max_tokens = max(max_tokens, tokens)
        heading = chunk.headings[0][:40] if chunk.headings else "(kein)"
        # Erste 80 Zeichen, Newlines ersetzen
        preview = chunk.text[:80].replace("\n", " ").strip()
        tbl = " [TBL]" if chunk.is_table else ""
        print(f"{chunk.chunk_index:4d} {tokens:6d} {len(chunk.text):7,} {heading:>40}  {preview}{tbl}")

    # --- 6. Zusammenfassung ---
    token_counts = [count_tokens(c.text) for c in filtered]
    print(f"\n=== ZUSAMMENFASSUNG ===")
    print(f"  Chunks total:     {len(filtered)}")
    print(f"  Avg Tokens:       {sum(token_counts) / len(token_counts):.0f}")
    print(f"  Min Tokens:       {min(token_counts)}")
    print(f"  Max Tokens:       {max(token_counts)}")
    print(f"  Max > 768?:       {'JA — PROBLEM!' if max_tokens > 768 else 'NEIN — OK'}")

    # Kapitel-Check
    kapitel_headings = [
        h for c in filtered for h in c.headings
        if re.match(r"\d+(\.\d+)*\.?\s+\w", h)
    ]
    unique_chapters = sorted(set(kapitel_headings))
    print(f"  Kapitel erkannt:  {len(unique_chapters)}")
    for ch in unique_chapters[:15]:
        print(f"    - {ch[:70]}")


if __name__ == "__main__":
    main()
