"""Tests fuer DoclingExtractor mit echtem Test-PDF (test_anlage_roboter.pdf).

Prueft End-to-End-Extraktion: Inhalt, Tabellen, Metadaten und Fehlerbehandlung.
Docling-Initialisierung ist langsam -- daher wird das Ergebnis als
module-level Fixture nur einmal berechnet.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from halle_gehirn.extraction.base import ExtractedDoc, ExtractionError
from halle_gehirn.extraction.docling_extractor import DoclingExtractor

TEST_DATA_DIR = Path(__file__).resolve().parent / "data"
TEST_PDF = TEST_DATA_DIR / "test_anlage_roboter.pdf"


@pytest.fixture(scope="module")
def extracted_doc() -> ExtractedDoc:
    """Extrahiert das Test-PDF einmalig fuer alle Tests im Modul."""
    assert TEST_PDF.exists(), f"Test-PDF nicht gefunden: {TEST_PDF}"
    extractor = DoclingExtractor()
    return extractor.extract(TEST_PDF)


class TestDoclingExtractPdf:
    """End-to-End-Tests gegen das UR10e-Test-PDF."""

    def test_docling_extract_pdf_not_empty(
        self, extracted_doc: ExtractedDoc,
    ) -> None:
        """body_md ist nicht leer und enthaelt substanziellen Inhalt (>200 Zeichen)."""
        assert extracted_doc.body_md, "body_md darf nicht leer sein"
        assert len(extracted_doc.body_md) > 200, (
            f"body_md zu kurz ({len(extracted_doc.body_md)} Zeichen, erwartet >200)"
        )

    def test_docling_extract_pdf_table_found(
        self, extracted_doc: ExtractedDoc,
    ) -> None:
        """Mindestens eine Tabelle wird extrahiert; Markdown enthaelt Pipe-Zeichen."""
        assert len(extracted_doc.tables) >= 1, "Keine Tabelle extrahiert"
        first_table_md = extracted_doc.tables[0].markdown
        assert "|" in first_table_md, (
            "Tabellen-Markdown enthaelt keine Pipe-Zeichen"
        )

    def test_docling_extract_pdf_metadata(
        self, extracted_doc: ExtractedDoc,
    ) -> None:
        """page_count == 1, source_type == pdf, language == de."""
        assert extracted_doc.page_count == 1, (
            f"Erwartete 1 Seite, bekam {extracted_doc.page_count}"
        )
        assert extracted_doc.source_type == "pdf", (
            f"Erwarteter source_type 'pdf', bekam '{extracted_doc.source_type}'"
        )
        assert extracted_doc.language == "de", (
            f"Erwartete Sprache 'de', bekam '{extracted_doc.language}'"
        )

    def test_docling_extract_pdf_table_content(
        self, extracted_doc: ExtractedDoc,
    ) -> None:
        """Tabelle enthaelt erwartete Werte aus dem UR10e-Datenblatt."""
        all_table_md = " ".join(t.markdown for t in extracted_doc.tables)
        expected_values = ["12,5", "1300", "IP54"]
        for value in expected_values:
            assert value in all_table_md, (
                f"Erwarteter Wert '{value}' nicht in Tabellen-Markdown gefunden"
            )


class TestDoclingExtractErrors:
    """Tests fuer Fehlerbehandlung des DoclingExtractors."""

    def test_docling_extract_nonexistent_raises(self) -> None:
        """FileNotFoundError bei nicht existierender Datei."""
        extractor = DoclingExtractor()
        with pytest.raises(FileNotFoundError):
            extractor.extract(Path("/tmp/does_not_exist_12345.pdf"))

    def test_docling_extract_unsupported_format_raises(
        self, tmp_path: Path,
    ) -> None:
        """ExtractionError bei nicht unterstuetztem Dateiformat (.xyz)."""
        dummy_file = tmp_path / "dummy.xyz"
        dummy_file.write_text("dummy content", encoding="utf-8")
        extractor = DoclingExtractor()
        with pytest.raises(ExtractionError):
            extractor.extract(dummy_file)
