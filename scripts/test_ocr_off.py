"""Diagnoseskript: Docling mit force_backend_text und reduzierter images_scale."""
from __future__ import annotations

import sys
import time
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root / "src"))

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableFormerMode,
    TableStructureOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

PDF_PATH = (
    _project_root
    / "data"
    / "manual"
    / "abschlussarbeiten"
    / "Abschlussarbeit_Zhili Wang.pdf"
)


def run_docling(label: str, **kwargs: object) -> None:
    """Extraktion mit gegebenen PdfPipelineOptions."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")

    pipeline_options = PdfPipelineOptions(
        do_table_structure=False,
        do_ocr=False,
        generate_picture_images=False,
        **kwargs,
    )
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        },
    )

    t0 = time.perf_counter()
    try:
        result = converter.convert(str(PDF_PATH))
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        print(f"  CRASH nach {elapsed:.1f}s: {type(exc).__name__}: {exc}")
        return

    elapsed = time.perf_counter() - t0
    print(f"  Status:          {result.status}")
    print(f"  Dauer:           {elapsed:.1f}s")

    n_errors = len(result.errors)
    n_pages_ok = len(result.pages)
    print(f"  Seiten OK:       {n_pages_ok}")
    print(f"  Fehler:          {n_errors}")

    doc = result.document
    body_md = doc.export_to_markdown()
    tables = list(getattr(doc, "tables", []))

    print(f"  Seiten (doc):    {len(getattr(doc, 'pages', {}))}")
    print(f"  MD-Zeichen:      {len(body_md):,}")
    print(f"  MD-Zeilen:       {body_md.count(chr(10)):,}")
    print(f"  Tabellen:        {len(tables)}")

    if n_errors == 0:
        # Vorschau bei Erfolg
        preview = body_md[:300].replace("\n", "\n    ")
        print(f"\n  Vorschau:\n    {preview}")
        tail = body_md[-300:].replace("\n", "\n    ")
        print(f"\n  Ende:\n    {tail}")


if __name__ == "__main__":
    if not PDF_PATH.exists():
        print(f"FEHLER: PDF nicht gefunden: {PDF_PATH}")
        sys.exit(1)

    # Test 1: force_backend_text=True (PDF-Backend-Text direkt, kein Bitmap-Rendering)
    run_docling("force_backend_text=True", force_backend_text=True)

    # Test 2: images_scale=0.25 (reduzierte Aufloesung)
    run_docling("images_scale=0.25", images_scale=0.25)

    # Test 3: force_backend_text=True + do_table_structure=True
    run_docling(
        "force_backend_text=True + Tables=FAST",
        force_backend_text=True,
        do_table_structure=True,
    )
