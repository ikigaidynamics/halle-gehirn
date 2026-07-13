"""Tests fuer den Chunk-Filter (Front-Matter, TOC, Min-Chars)."""
from __future__ import annotations

from halle_gehirn.pipeline.chunk_filter import filter_chunks
from halle_gehirn.pipeline.chunker import Chunk


def _make_chunk(
    text: str,
    index: int = 0,
    headings: list[str] | None = None,
    is_table: bool = False,
    char_start: int = 0,
) -> Chunk:
    """Helfer: Erstellt einen Chunk mit Mindestfeldern."""
    return Chunk(
        text=text,
        char_start=char_start,
        char_end=char_start + len(text),
        chunk_index=index,
        headings=headings or [],
        is_table=is_table,
    )


class TestMinChars:
    """Tests fuer die Mindestlaenge-Regel."""

    def test_short_chunks_dropped(self) -> None:
        """Chunks unter min_chunk_chars werden verworfen."""
        chunks = [
            _make_chunk("OK " * 50, index=0),  # 150 Zeichen
            _make_chunk("Kurz", index=1),        # 4 Zeichen
        ]
        result = filter_chunks(chunks)
        assert len(result) == 1
        assert result[0].chunk_index == 0

    def test_short_table_not_dropped(self) -> None:
        """Kurze Tabellen-Chunks werden NICHT verworfen."""
        chunks = [_make_chunk("| A |\n|---|\n| 1 |", is_table=True)]
        result = filter_chunks(chunks)
        assert len(result) == 1

    def test_normal_content_kept(self) -> None:
        """Normaler Fachtext wird nicht verworfen."""
        text = "Dies ist ein normaler Absatz mit genuegend Inhalt. " * 5
        chunks = [_make_chunk(text)]
        result = filter_chunks(chunks)
        assert len(result) == 1


class TestTOCDetection:
    """Tests fuer Verzeichnis-Erkennung."""

    def test_toc_heading_dropped(self) -> None:
        """Chunks mit Inhaltsverzeichnis-Heading werden verworfen."""
        chunks = [
            _make_chunk(
                "## Inhaltsverzeichnis\n\n1. Einleitung\n2. Methode",
                headings=["Inhaltsverzeichnis"],
            ),
            _make_chunk("Normaler Inhalt " * 20, index=1),
        ]
        result = filter_chunks(chunks)
        assert len(result) == 1

    def test_abbildungsverzeichnis_dropped(self) -> None:
        """Abbildungsverzeichnis-Chunks werden verworfen."""
        chunks = [_make_chunk(
            "## Abbildungsverzeichnis\n\nAbb 1 zeigt die Anlage. " * 5,
            headings=["Abbildungsverzeichnis"],
        )]
        result = filter_chunks(chunks)
        assert len(result) == 0

    def test_literaturverzeichnis_dropped(self) -> None:
        """Literaturverzeichnis wird verworfen."""
        chunks = [_make_chunk(
            "## Literaturverzeichnis\n\n[1] Mueller, 2024. " * 5,
            headings=["Literaturverzeichnis"],
        )]
        result = filter_chunks(chunks)
        assert len(result) == 0


class TestDotLeaders:
    """Tests fuer die Punktreihen-Heuristik."""

    def test_dot_leader_content_dropped(self) -> None:
        """Inhalte mit vielen Punktreihen werden verworfen."""
        lines = [
            f"Kapitel {i} {'.' * 30} {i + 10}" for i in range(10)
        ]
        text = "\n".join(lines)
        chunks = [_make_chunk(text)]
        result = filter_chunks(chunks)
        assert len(result) == 0

    def test_normal_text_not_affected(self) -> None:
        """Normaler Text ohne Punktreihen bleibt erhalten."""
        text = "Dies ist ein normaler Absatz ohne Punkte. " * 10
        chunks = [_make_chunk(text)]
        result = filter_chunks(chunks)
        assert len(result) == 1


class TestFrontMatter:
    """Tests fuer den Front-Matter-Filter (abschlussarbeit)."""

    def test_front_matter_before_numbered_heading_dropped(self) -> None:
        """Chunks vor dem ersten nummerierten Heading werden verworfen."""
        chunks = [
            # Chunk 0: Deckblatt mit Heading (wie "## Elektrotechnik")
            _make_chunk(
                "## Elektrotechnik\n\nFachbereich ET.",
                index=0,
                headings=["Elektrotechnik"],
                char_start=0,
            ),
            # Chunk 1: Gutachter-Block (char_start > 0)
            _make_chunk(
                "Erstgutachter: Prof. Dr. Berger\n\nZweitgutachter: M.Eng. Lautsch",
                index=1,
                char_start=191,
            ),
            # Chunk 2: Erstes echtes Kapitel (>100 Zeichen)
            _make_chunk(
                "## 1 Einleitung\n\nDiese Arbeit behandelt die vorausschauende Wartung industrieller Anlagen mittels IIoT und kuenstlicher Intelligenz.",
                index=2,
                headings=["1 Einleitung"],
                char_start=500,
            ),
            # Chunk 3: Weiterer Inhalt
            _make_chunk(
                "## 2 Theoretischer Hintergrund\n\nWartung ist wichtig. " * 5,
                index=3,
                headings=["2 Theoretischer Hintergrund"],
                char_start=1200,
            ),
        ]
        result = filter_chunks(chunks, doc_type="abschlussarbeit")
        # Chunks 0 und 1 verworfen, Chunks 2 und 3 behalten
        assert len(result) == 2
        assert "1 Einleitung" in result[0].text
        assert "2 Theoretischer Hintergrund" in result[1].text
        # Indices neu vergeben
        assert result[0].chunk_index == 0
        assert result[1].chunk_index == 1

    def test_front_matter_fallback_no_numbered_heading(self) -> None:
        """Ohne nummeriertes Heading wird nichts als Front-Matter verworfen."""
        chunks = [
            _make_chunk(
                "## Zusammenfassung\n\nDiese Arbeit beschreibt ein System. " * 5,
                index=0,
                headings=["Zusammenfassung"],
            ),
            _make_chunk(
                "## Methode\n\nWir verwenden Python und OPC UA. " * 5,
                index=1,
                headings=["Methode"],
            ),
        ]
        result = filter_chunks(chunks, doc_type="abschlussarbeit")
        # Kein Chunk verworfen (kein nummeriertes Heading)
        assert len(result) == 2

    def test_front_matter_only_for_abschlussarbeit(self) -> None:
        """Front-Matter-Filter greift NICHT bei anderen doc_types."""
        chunks = [
            _make_chunk("Kurzer Vorspann. " * 10, index=0),
            _make_chunk(
                "## 1 Einleitung\n\nText hier. " * 10,
                index=1,
                headings=["1 Einleitung"],
            ),
        ]
        result = filter_chunks(chunks, doc_type="handbuch")
        # Beide behalten (kein Front-Matter-Filter fuer handbuch)
        assert len(result) == 2


class TestReindexing:
    """Tests fuer die Re-Indizierung nach Filterung."""

    def test_indices_renumbered(self) -> None:
        """Nach Filterung werden chunk_index fortlaufend ab 0 vergeben."""
        chunks = [
            _make_chunk("Kurz", index=0),       # verworfen (zu kurz)
            _make_chunk("Langer Inhalt " * 20, index=1),
            _make_chunk("Noch mehr Inhalt " * 20, index=2),
        ]
        result = filter_chunks(chunks)
        assert [c.chunk_index for c in result] == [0, 1]
