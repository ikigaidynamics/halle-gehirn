"""Findet Chunks ueber 768 Token in der Abschlussarbeit.

Zeigt: Token-Zahl, Heading/Breadcrumb, erste 200 Zeichen.
Vergleicht vor und nach filter_chunks.
Nutzt pymupdf4llm direkt (Docling wird uebersprungen — gleicher Output).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["OLLAMA_URL"] = "http://localhost:11434"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pymupdf4llm

from halle_gehirn.config import get_settings
from halle_gehirn.extraction.base import ExtractedDoc
from halle_gehirn.pipeline.chunk_filter import filter_chunks
from halle_gehirn.pipeline.chunker import MarkdownChunker, count_tokens

settings = get_settings()

PDF = Path("data/manual/abschlussarbeiten/Abschlussarbeit_Zhili Wang.pdf")
MAX = settings.chunk_max_tokens  # 768

# Extrahieren via pymupdf4llm (gleicher Output wie der Fallback)
print("Extrahiere via pymupdf4llm...")
md = pymupdf4llm.to_markdown(str(PDF))
print(f"Extrahiert: {len(md)} Zeichen")

doc = ExtractedDoc(
    title="Abschlussarbeit_Zhili Wang",
    body_md=md,
    tables=[],
    source=str(PDF),
    source_type="pdf",
    meta={"extraction_backend": "pymupdf4llm"},
)

# Chunken (vor Filter)
chunker = MarkdownChunker(settings=settings)
raw_chunks = chunker.chunk(doc, doc_type="abschlussarbeit")
print(f"\nRaw Chunks: {len(raw_chunks)}")

# Oversized VOR Filter
oversized_raw = [(i, c) for i, c in enumerate(raw_chunks) if count_tokens(c.text) > MAX]
print(f"Oversized (> {MAX} Token) VOR Filter: {len(oversized_raw)}")
for idx, chunk in oversized_raw:
    tokens = count_tokens(chunk.text)
    heading = " > ".join(chunk.headings) if chunk.headings else "(kein Heading)"
    preview = chunk.text[:200].replace("\n", " ")
    print(f"\n  Chunk #{idx}: {tokens} Token")
    print(f"  Heading: {heading}")
    print(f"  Preview: {preview}")

# Filtern
filtered = filter_chunks(raw_chunks, doc_type="abschlussarbeit", settings=settings)
print(f"\nNach Filter: {len(filtered)}")

# Oversized NACH Filter
oversized_filtered = [(i, c) for i, c in enumerate(filtered) if count_tokens(c.text) > MAX]
print(f"Oversized (> {MAX} Token) NACH Filter: {len(oversized_filtered)}")
for idx, chunk in oversized_filtered:
    tokens = count_tokens(chunk.text)
    heading = " > ".join(chunk.headings) if chunk.headings else "(kein Heading)"
    preview = chunk.text[:200].replace("\n", " ")
    print(f"\n  Chunk #{idx}: {tokens} Token")
    print(f"  Heading: {heading}")
    print(f"  Preview: {preview}")

# Wurden Oversized-Chunks rausgefiltert?
raw_ids = {id(c) for _, c in oversized_raw}
filtered_ids = {id(c) for c in filtered}
for idx, chunk in oversized_raw:
    in_filtered = id(chunk) in filtered_ids
    tokens = count_tokens(chunk.text)
    heading = " > ".join(chunk.headings) if chunk.headings else "(kein Heading)"
    status = "PASSIERT Filter" if in_filtered else "GEFILTERT (erreicht Embedder NICHT)"
    print(f"\n  Chunk #{idx} ({tokens} Token, '{heading}'): {status}")

print("\nFazit: embedding_text_oversized Warnung haette",
      "NICHT gefeuert" if all(id(c) not in filtered_ids for _, c in oversized_raw) else "gefeuert",
      "fuer die oversized Chunks")
