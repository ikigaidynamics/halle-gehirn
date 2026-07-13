"""Tests fuer WP3: Seiten-Provenienz (Page-Map) + Boilerplate-Wiring.

- build_page_map: monotones Element-Matching im Markdown
- page_for_offset: Offset → Seite (bisect)
- join_pages_with_map: exakte Map fuer seitenweise Backends
- remove_cross_page_repeats: Kopf-/Fusszeilen ueber Seiten
- Chunker weist Body-Chunks Seiten aus doc.page_map zu
- pymupdf4llm-Fallback liefert Page-Map (echte Test-PDF)
"""
from __future__ import annotations

from pathlib import Path

from halle_gehirn.config import Settings
from halle_gehirn.extraction.base import ExtractedDoc
from halle_gehirn.extraction.page_map import (
    build_page_map,
    join_pages_with_map,
    page_for_offset,
    remove_cross_page_repeats,
)
from halle_gehirn.pipeline.chunker import MarkdownChunker

TEST_PDF = Path(__file__).parent / "data" / "test_anlage_roboter.pdf"


class TestBuildPageMap:
    """Monotones Element-Matching im Markdown."""

    def test_basic_mapping(self) -> None:
        """Elemente werden in Reihenfolge gefunden, Map je Seitenwechsel."""
        body = "## Einleitung\n\nErster Text.\n\n## Methode\n\nZweiter Text."
        elements: list[tuple[str, int | None]] = [
            ("Einleitung", 1),
            ("Erster Text.", 1),
            ("Methode", 2),
            ("Zweiter Text.", 2),
        ]
        page_map = build_page_map(body, elements)
        assert len(page_map) == 2
        assert page_map[0][1] == 1
        assert page_map[1][1] == 2
        # Seite 2 beginnt beim Methode-Heading
        assert page_map[1][0] == body.index("Methode")

    def test_unmatched_elements_skipped(self) -> None:
        """Nicht auffindbare Elemente brechen die Map nicht."""
        body = "Nur dieser Text existiert."
        elements: list[tuple[str, int | None]] = [
            ("Nur dieser Text", 1),
            ("Gibt es nicht im Body", 2),
        ]
        page_map = build_page_map(body, elements)
        assert page_map == [(0, 1)]

    def test_none_page_skipped(self) -> None:
        """Elemente ohne Seitennummer werden ignoriert."""
        body = "Text A. Text B."
        elements: list[tuple[str, int | None]] = [
            ("Text A.", None),
            ("Text B.", 3),
        ]
        page_map = build_page_map(body, elements)
        assert page_map == [(body.index("Text B."), 3)]

    def test_whitespace_normalized_needle(self) -> None:
        """Element-Text mit Zeilenumbruechen matcht normalisiert nicht —
        wird uebersprungen statt falsch zu matchen."""
        body = "Ein langer Satz ohne Umbruch."
        elements: list[tuple[str, int | None]] = [
            ("Ein langer\nSatz", 1),
        ]
        # Normalisierung macht "Ein langer Satz" daraus → matcht
        page_map = build_page_map(body, elements)
        assert page_map == [(0, 1)]


class TestPageForOffset:
    """Offset → Seite via bisect."""

    def test_lookup(self) -> None:
        """Offsets zwischen Eintraegen liefern die richtige Seite."""
        page_map = [(0, 1), (100, 2), (250, 4)]
        assert page_for_offset(page_map, 0) == 1
        assert page_for_offset(page_map, 99) == 1
        assert page_for_offset(page_map, 100) == 2
        assert page_for_offset(page_map, 249) == 2
        assert page_for_offset(page_map, 9999) == 4

    def test_before_first_entry(self) -> None:
        """Offsets vor dem ersten Eintrag → erste bekannte Seite."""
        page_map = [(50, 2)]
        assert page_for_offset(page_map, 10) == 2

    def test_empty_map(self) -> None:
        """Leere Map → None."""
        assert page_for_offset([], 42) is None


class TestJoinPagesWithMap:
    """Exakte Page-Map fuer seitenweise Backends (pymupdf4llm)."""

    def test_join_and_offsets(self) -> None:
        """Offsets zeigen exakt auf die Seitenanfaenge."""
        pages = ["Seite eins Inhalt.", "Seite zwei Inhalt."]
        body, page_map = join_pages_with_map(pages)
        assert body == "Seite eins Inhalt.\n\nSeite zwei Inhalt."
        assert page_map == [(0, 1), (20, 2)]
        assert body[20:] == "Seite zwei Inhalt."

    def test_empty_page_keeps_numbering(self) -> None:
        """Leere Seite wird uebersprungen, Nummern bleiben original."""
        pages = ["Inhalt A.", "", "Inhalt C."]
        _body, page_map = join_pages_with_map(pages)
        assert [p for _, p in page_map] == [1, 3]


class TestCrossPageRepeats:
    """Kopf-/Fusszeilen-Entfernung ueber Seiten hinweg."""

    def test_repeated_header_removed(self) -> None:
        """Zeile auf >=3 Seiten wird ueberall entfernt."""
        pages = [
            f"Masterarbeit Bahnplanung | BTU\n\nInhalt Seite {i}."
            for i in range(1, 5)
        ]
        cleaned = remove_cross_page_repeats(pages)
        for page in cleaned:
            assert "Masterarbeit Bahnplanung | BTU" not in page
        assert "Inhalt Seite 2." in cleaned[1]

    def test_unique_lines_kept(self) -> None:
        """Ohne Wiederholungen bleibt alles unveraendert."""
        pages = ["Seite A Text.", "Seite B Text."]
        assert remove_cross_page_repeats(pages) == pages


class TestChunkerPageAssignment:
    """Der Chunker weist Body-Chunks Seiten aus doc.page_map zu."""

    def _doc(self, body: str, page_map: list[tuple[int, int]]) -> ExtractedDoc:
        return ExtractedDoc(
            source="/test/doc.pdf",
            source_type="pdf",
            title="Test",
            body_md=body,
            page_map=page_map,
        )

    def test_pages_assigned_from_map(self) -> None:
        """Chunks tragen die Seite ihres char_start."""
        body = (
            "## Kapitel Eins\n\nInhalt des ersten Kapitels hier.\n\n"
            "## Kapitel Zwei\n\nInhalt des zweiten Kapitels hier.\n"
        )
        page_map = [(0, 1), (body.index("Kapitel Zwei") - 3, 5)]
        chunker = MarkdownChunker()
        chunks = chunker.chunk(self._doc(body, page_map))
        pages = {c.headings[-1]: c.page for c in chunks if c.headings}
        assert pages["Kapitel Eins"] == 1
        assert pages["Kapitel Zwei"] == 5

    def test_no_map_no_pages(self) -> None:
        """Ohne Page-Map bleiben Body-Chunks ohne Seite."""
        chunker = MarkdownChunker()
        chunks = chunker.chunk(self._doc("## A\n\nEin Text.", []))
        assert all(c.page is None for c in chunks)


class TestDoclingBuildResult:
    """Docling-Primaerpfad: Cleaning + Page-Map in _build_result."""

    def test_clean_and_page_map(self, tmp_path: Path) -> None:
        """Seitenzahl-Zeilen bereinigt, Page-Map aus Element-Provenienz."""
        from types import SimpleNamespace

        from halle_gehirn.extraction.docling_extractor import DoclingExtractor

        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-fake")
        body = (
            "## Einleitung\n\nText auf Seite eins.\n\n"
            "- 3 -\n\n"
            "## Methode\n\nText auf Seite zwei."
        )
        texts = [
            SimpleNamespace(text="Einleitung", prov=[SimpleNamespace(page_no=1)]),
            SimpleNamespace(
                text="Text auf Seite eins.", prov=[SimpleNamespace(page_no=1)],
            ),
            SimpleNamespace(text="Methode", prov=[SimpleNamespace(page_no=2)]),
            SimpleNamespace(
                text="Text auf Seite zwei.", prov=[SimpleNamespace(page_no=2)],
            ),
        ]
        fake_doc = SimpleNamespace(
            export_to_markdown=lambda: body,
            texts=texts,
            tables=[],
            pictures=[],
            pages={1: None, 2: None},
            name="Testdokument",
        )
        extractor = DoclingExtractor(
            settings=Settings(boilerplate_clean=True),
        )
        doc = extractor._build_result(fake_doc, pdf)

        assert "- 3 -" not in doc.body_md, "Seitenzahl-Zeile nicht bereinigt"
        assert [p for _, p in doc.page_map] == [1, 2]
        assert doc.page_count == 2
        # Offsets zeigen auf die richtigen Stellen im BEREINIGTEN Body
        offset_p2 = doc.page_map[1][0]
        assert doc.body_md[offset_p2:].startswith("Methode")


class TestPymupdfFallbackPageMap:
    """Integrationstest: Fallback liefert Page-Map (echte Test-PDF)."""

    def test_fallback_has_page_map(self) -> None:
        """_pymupdf_fallback baut body_md + exakte Page-Map."""
        if not TEST_PDF.exists():
            import pytest
            pytest.skip("Test-PDF fehlt")
        from halle_gehirn.extraction.docling_extractor import DoclingExtractor

        extractor = DoclingExtractor(settings=Settings())
        doc = extractor._pymupdf_fallback(TEST_PDF)
        assert doc.body_md
        assert doc.page_map, "Fallback muss eine Page-Map liefern"
        assert doc.meta["extraction_backend"] == "pymupdf4llm"
        # Jeder Map-Eintrag zeigt auf gueltigen Offset
        for offset, page in doc.page_map:
            assert 0 <= offset < len(doc.body_md)
            assert page >= 1
