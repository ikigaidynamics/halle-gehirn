"""Tests fuer halle_gehirn.extraction.plaintext_extractor.

Prueft: .md- und .txt-Extraktion, Titelextraktion, Fehlerbehandlung.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from halle_gehirn.extraction.base import ExtractionError
from halle_gehirn.extraction.plaintext_extractor import PlaintextExtractor


@pytest.fixture()
def extractor() -> PlaintextExtractor:
    """Erzeugt einen PlaintextExtractor."""
    return PlaintextExtractor()


# ────────────────────────── .md ──────────────────────────


class TestMarkdownExtraction:
    """Tests fuer .md-Dateien."""

    def test_body_preserved(self, tmp_path: Path, extractor: PlaintextExtractor) -> None:
        """Markdown-Inhalt wird als-is uebernommen."""
        content = "# Heading\n\nSome **bold** text.\n"
        md = tmp_path / "test.md"
        md.write_text(content, encoding="utf-8")
        doc = extractor.extract(md)
        assert doc.body_md == content

    def test_title_from_heading(self, tmp_path: Path, extractor: PlaintextExtractor) -> None:
        """Titel wird aus erstem # Heading extrahiert."""
        md = tmp_path / "test.md"
        md.write_text("# Mein Titel\n\nText.", encoding="utf-8")
        doc = extractor.extract(md)
        assert doc.title == "Mein Titel"

    def test_title_fallback_to_filename(self, tmp_path: Path, extractor: PlaintextExtractor) -> None:
        """Ohne # Heading wird der Dateiname als Titel verwendet."""
        md = tmp_path / "roboter_doku.md"
        md.write_text("Kein Heading hier.\n", encoding="utf-8")
        doc = extractor.extract(md)
        assert doc.title == "roboter_doku"

    def test_source_type(self, tmp_path: Path, extractor: PlaintextExtractor) -> None:
        """source_type ist 'md'."""
        md = tmp_path / "test.md"
        md.write_text("text", encoding="utf-8")
        doc = extractor.extract(md)
        assert doc.source_type == "md"

    def test_tables_empty(self, tmp_path: Path, extractor: PlaintextExtractor) -> None:
        """Keine Tabellen bei Plaintext."""
        md = tmp_path / "test.md"
        md.write_text("text", encoding="utf-8")
        doc = extractor.extract(md)
        assert doc.tables == []

    def test_page_count_none(self, tmp_path: Path, extractor: PlaintextExtractor) -> None:
        """Keine Seitenzahl bei Plaintext."""
        md = tmp_path / "test.md"
        md.write_text("text", encoding="utf-8")
        doc = extractor.extract(md)
        assert doc.page_count is None

    def test_meta_has_file_info(self, tmp_path: Path, extractor: PlaintextExtractor) -> None:
        """Meta enthaelt Dateiinformationen."""
        md = tmp_path / "test.md"
        md.write_text("text", encoding="utf-8")
        doc = extractor.extract(md)
        assert doc.meta["file_name"] == "test.md"
        assert "file_size_bytes" in doc.meta


# ────────────────────────── .txt ──────────────────────────


class TestTxtExtraction:
    """Tests fuer .txt-Dateien."""

    def test_body_is_content(self, tmp_path: Path, extractor: PlaintextExtractor) -> None:
        """Textinhalt wird als body_md uebernommen."""
        content = "Einfacher Text mit Absaetzen.\n\nZweiter Absatz.\n"
        txt = tmp_path / "notizen.txt"
        txt.write_text(content, encoding="utf-8")
        doc = extractor.extract(txt)
        assert doc.body_md == content

    def test_title_is_filename(self, tmp_path: Path, extractor: PlaintextExtractor) -> None:
        """Titel ist der Dateiname (ohne Endung)."""
        txt = tmp_path / "wartungsprotokoll.txt"
        txt.write_text("text", encoding="utf-8")
        doc = extractor.extract(txt)
        assert doc.title == "wartungsprotokoll"

    def test_source_type(self, tmp_path: Path, extractor: PlaintextExtractor) -> None:
        """source_type ist 'txt'."""
        txt = tmp_path / "test.txt"
        txt.write_text("text", encoding="utf-8")
        doc = extractor.extract(txt)
        assert doc.source_type == "txt"


# ────────────────────────── Fehler ──────────────────────────


class TestPlaintextErrors:
    """Tests fuer Fehlerbehandlung."""

    def test_nonexistent_file(self, tmp_path: Path, extractor: PlaintextExtractor) -> None:
        """Nicht existierende Datei wirft ExtractionError."""
        with pytest.raises(ExtractionError, match="nicht gefunden"):
            extractor.extract(tmp_path / "gibts_nicht.md")

    def test_unsupported_extension(self, tmp_path: Path, extractor: PlaintextExtractor) -> None:
        """Nicht unterstuetzte Endung wirft ExtractionError."""
        f = tmp_path / "test.xyz"
        f.write_text("text", encoding="utf-8")
        with pytest.raises(ExtractionError, match="Nicht unterstuetztes Format"):
            extractor.extract(f)


# ────────────────────────── Protocol ──────────────────────────


class TestProtocolConformance:
    """Tests fuer Protocol-Konformitaet."""

    def test_supported_extensions(self, extractor: PlaintextExtractor) -> None:
        """supported_extensions gibt .md und .txt zurueck."""
        assert extractor.supported_extensions == frozenset({".md", ".txt"})

    def test_implements_extractor_protocol(self, extractor: PlaintextExtractor) -> None:
        """PlaintextExtractor implementiert das Extractor-Protocol."""
        from halle_gehirn.extraction.base import Extractor
        assert isinstance(extractor, Extractor)
