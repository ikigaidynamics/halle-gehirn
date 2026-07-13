"""Integrationstest: Prueft ob die fail-closed Logik + Fallback funktioniert."""
from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root / "src"))

from halle_gehirn.extraction.docling_extractor import DoclingExtractor

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
    print()

    extractor = DoclingExtractor()

    print("=== Extraktion mit fail-closed + Fallback (OCR=off) ===")
    doc = extractor.extract(PDF_PATH, do_ocr=False)

    print(f"  Titel:            {doc.title}")
    print(f"  Source-Type:      {doc.source_type}")
    print(f"  Seiten:           {doc.page_count}")
    print(f"  MD-Zeichen:       {len(doc.body_md):,}")
    print(f"  MD-Zeilen:        {doc.body_md.count(chr(10)):,}")
    print(f"  Tabellen:         {len(doc.tables)}")
    print(f"  Backend:          {doc.meta.get('extraction_backend', 'docling')}")
    print(f"  Sprache:          {doc.language}")
    print()

    # Sanity check: Ein 111-Seiten-PDF muss mindestens 50.000 Zeichen haben
    min_chars = 50_000
    if len(doc.body_md) < min_chars:
        print(f"  FEHLER: Nur {len(doc.body_md):,} Zeichen — unter Minimum von {min_chars:,}")
        sys.exit(1)
    else:
        print(f"  OK: {len(doc.body_md):,} Zeichen (Minimum: {min_chars:,})")

    # Vorschau
    print()
    preview = doc.body_md[:500].replace("\n", "\n    ")
    print(f"  Vorschau:\n    {preview}")


if __name__ == "__main__":
    main()
