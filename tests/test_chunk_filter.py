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


class TestTailMatter:
    """Tests fuer den Tail-Matter-Filter (Anhang, Literaturverzeichnis)."""

    def test_anhang_and_following_chunks_dropped(self) -> None:
        """Chunks ab 'Anhang' werden verworfen (abschlussarbeit)."""
        chunks = [
            _make_chunk(
                "## 1 Einleitung\n\nText hier. " * 10,
                index=0,
                headings=["1 Einleitung"],
            ),
            _make_chunk(
                "## 2 Methode\n\nBeschreibung der Methode. " * 10,
                index=1,
                headings=["2 Methode"],
            ),
            _make_chunk(
                "## Anhang\n\nAnhang A: Tabellen. " * 10,
                index=2,
                headings=["Anhang"],
            ),
            _make_chunk(
                "## A.1 Zusaetzliche Diagramme\n\nDiagramm 1. " * 10,
                index=3,
                headings=["A.1 Zusaetzliche Diagramme"],
            ),
        ]
        result = filter_chunks(chunks, doc_type="abschlussarbeit")
        assert len(result) == 2
        assert "Einleitung" in result[0].text
        assert "Methode" in result[1].text

    def test_literaturverzeichnis_and_following_dropped(self) -> None:
        """Chunks ab 'Literaturverzeichnis' werden verworfen."""
        chunks = [
            _make_chunk(
                "## 1 Einleitung\n\nForschungsfrage. " * 10,
                index=0,
                headings=["1 Einleitung"],
            ),
            _make_chunk(
                "## 5 Literaturverzeichnis\n\n[1] Mueller. " * 10,
                index=1,
                headings=["5 Literaturverzeichnis"],
            ),
            _make_chunk(
                "[2] Schmidt, 2023. Weitere Referenz. " * 10,
                index=2,
            ),
        ]
        result = filter_chunks(chunks, doc_type="abschlussarbeit")
        assert len(result) == 1
        assert "Einleitung" in result[0].text

    def test_tail_matter_only_for_thesis_types(self) -> None:
        """Tail-Matter-Filter greift NICHT bei anderen doc_types."""
        chunks = [
            _make_chunk("Inhalt " * 20, index=0),
            _make_chunk(
                "## Anhang\n\nZusaetzliche Infos. " * 10,
                index=1,
                headings=["Anhang"],
            ),
        ]
        result = filter_chunks(chunks, doc_type="handbuch")
        # Anhang-Heading-Chunk wird per toc_heading (Regel 2) verworfen,
        # aber kein Tail-Matter-Filter aktiv
        assert len(result) == 1

    def test_eigenstaendigkeitserklaerung_dropped(self) -> None:
        """Eigenstaendigkeitserklaerung wird als Tail-Matter erkannt."""
        chunks = [
            _make_chunk(
                "## 1 Fazit\n\nZusammenfassung der Ergebnisse. " * 10,
                index=0,
                headings=["1 Fazit"],
            ),
            _make_chunk(
                "## Eigenständigkeitserklärung\n\nHiermit erklaere ich. " * 5,
                index=1,
                headings=["Eigenständigkeitserklärung"],
            ),
        ]
        result = filter_chunks(chunks, doc_type="abschlussarbeit")
        assert len(result) == 1
        assert "Fazit" in result[0].text

    def test_front_and_tail_matter_combined(self) -> None:
        """Front-Matter UND Tail-Matter in derselben Arbeit."""
        chunks = [
            _make_chunk("Deckblatt " * 20, index=0),
            _make_chunk(
                "## 1 Einleitung\n\nText. " * 10,
                index=1,
                headings=["1 Einleitung"],
            ),
            _make_chunk(
                "## 2 Ergebnis\n\nResultate. " * 10,
                index=2,
                headings=["2 Ergebnis"],
            ),
            _make_chunk(
                "## Literaturverzeichnis\n\nRef. " * 10,
                index=3,
                headings=["Literaturverzeichnis"],
            ),
            _make_chunk(
                "## Anhang\n\nTabelle. " * 10,
                index=4,
                headings=["Anhang"],
            ),
        ]
        result = filter_chunks(chunks, doc_type="abschlussarbeit")
        assert len(result) == 2
        assert "Einleitung" in result[0].text
        assert "Ergebnis" in result[1].text
        assert result[0].chunk_index == 0
        assert result[1].chunk_index == 1

    def test_numbered_tail_heading(self) -> None:
        """Nummeriertes Tail-Heading wie '7 Quellenverzeichnis'."""
        chunks = [
            _make_chunk(
                "## 1 Einleitung\n\nText. " * 10,
                index=0,
                headings=["1 Einleitung"],
            ),
            _make_chunk(
                "## 7 Quellenverzeichnis\n\n[1] Ref. " * 10,
                index=1,
                headings=["7 Quellenverzeichnis"],
            ),
        ]
        result = filter_chunks(chunks, doc_type="promotion")
        assert len(result) == 1
        assert "Einleitung" in result[0].text


class TestPositionalExemptions:
    """Ausnahmen vom positionalen Front-/Tail-Matter-Drop."""

    def test_tables_survive_tail_matter(self) -> None:
        """Tabellen-Chunks am Listenende fallen NICHT unter Tail-Matter."""
        chunks = [
            _make_chunk(
                "## 1 Einleitung\n\nText hier. " * 10,
                index=0,
                headings=["1 Einleitung"],
            ),
            _make_chunk(
                "## Literaturverzeichnis\n\n[1] Ref. " * 10,
                index=1,
                headings=["Literaturverzeichnis"],
            ),
            # Vom Chunker ans Ende gehaengte Ergebnistabelle
            _make_chunk(
                "| Messpunkt | Wert |\n|---|---|\n| P1 | 1,2 |",
                index=2,
                is_table=True,
            ),
        ]
        result = filter_chunks(chunks, doc_type="abschlussarbeit")
        assert len(result) == 2
        assert any(c.is_table for c in result)

    def test_tables_survive_front_matter(self) -> None:
        """Tabellen-Chunks fallen nicht unter den Front-Matter-Drop."""
        chunks = [
            _make_chunk(
                "| A | B |\n|---|---|\n| 1 | 2 |",
                index=0,
                is_table=True,
            ),
            _make_chunk(
                "## 1 Einleitung\n\nInhalt der Einleitung. " * 5,
                index=1,
                headings=["1 Einleitung"],
            ),
        ]
        result = filter_chunks(chunks, doc_type="abschlussarbeit")
        assert len(result) == 2

    def test_kurzfassung_survives_front_matter(self) -> None:
        """Kurzfassung vor Kapitel 1 bleibt im Index."""
        chunks = [
            _make_chunk("Deckblatt " * 20, index=0),
            _make_chunk(
                "## Kurzfassung\n\nDiese Arbeit optimiert die Bahnplanung. "
                * 5,
                index=1,
                headings=["Kurzfassung"],
            ),
            _make_chunk(
                "## Abstract\n\nThis thesis optimises path planning. " * 5,
                index=2,
                headings=["Abstract"],
            ),
            _make_chunk(
                "## 1 Einleitung\n\nText der Einleitung. " * 5,
                index=3,
                headings=["1 Einleitung"],
            ),
        ]
        result = filter_chunks(chunks, doc_type="abschlussarbeit")
        texts = "\n".join(c.text for c in result)
        assert len(result) == 3
        assert "Kurzfassung" in texts
        assert "Abstract" in texts
        assert "Deckblatt" not in texts

    def test_numbered_zusammenfassung_not_whitelisted(self) -> None:
        """Nummeriertes '7 Zusammenfassung' ist Inhalt, keine Kurzfassung.

        Die Whitelist greift nur fuer unnummerierte Headings; ein
        nummeriertes Kapitel liegt ohnehin nie vor front_matter_end.
        """
        chunks = [
            _make_chunk("Deckblatt " * 20, index=0),
            _make_chunk(
                "## 1 Einleitung\n\nText. " * 10,
                index=1,
                headings=["1 Einleitung"],
            ),
            _make_chunk(
                "## 7 Zusammenfassung\n\nErgebnisse. " * 10,
                index=2,
                headings=["7 Zusammenfassung"],
            ),
        ]
        result = filter_chunks(chunks, doc_type="abschlussarbeit")
        assert len(result) == 2  # Deckblatt weg, Kapitel bleiben


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
