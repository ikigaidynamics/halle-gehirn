"""Tests fuer den Markdown-Chunker (Chunk-Laengen, Tabellen, Offsets)."""
from __future__ import annotations

from halle_gehirn.extraction.base import ExtractedDoc, TableBlock
from halle_gehirn.pipeline.chunker import MarkdownChunker, count_tokens


def _make_doc(body: str, tables: list[TableBlock] | None = None) -> ExtractedDoc:
    """Helfer: Erstellt ein ExtractedDoc mit gegebenem Body."""
    return ExtractedDoc(
        source="/test/doc.pdf",
        source_type="pdf",
        title="Testdokument",
        body_md=body,
        tables=tables or [],
    )


class TestCountTokens:
    """Tests fuer die Token-Zaehlfunktion."""

    def test_count_tokens_nonempty(self) -> None:
        """Ein normaler Satz hat mehr als 0 Tokens."""
        assert count_tokens("Der Roboter bewegt sich.") > 0

    def test_count_tokens_empty(self) -> None:
        """Leerer String hat 0 Tokens."""
        assert count_tokens("") == 0


class TestMarkdownChunker:
    """Tests fuer den MarkdownChunker."""

    def test_short_doc_single_chunk(self) -> None:
        """Kurzes Dokument ergibt einen einzelnen Chunk."""
        doc = _make_doc("Ein kurzer Absatz.")
        chunker = MarkdownChunker()
        chunks = chunker.chunk(doc)
        assert len(chunks) == 1
        assert chunks[0].text == "Ein kurzer Absatz."
        assert chunks[0].chunk_index == 0

    def test_heading_sections_split(self) -> None:
        """Dokument mit Headings wird in Sections aufgeteilt."""
        body = (
            "## Einleitung\n\nErster Absatz.\n\n"
            "## Methode\n\nZweiter Absatz.\n\n"
            "## Ergebnis\n\nDritter Absatz.\n"
        )
        doc = _make_doc(body)
        chunker = MarkdownChunker()
        chunks = chunker.chunk(doc)
        assert len(chunks) >= 3
        # Jeder Chunk hat fortlaufenden Index
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_table_separate_chunk(self) -> None:
        """Tabellen werden als eigene Chunks behandelt."""
        table_md = "| Achse | Wert |\n|---|---|\n| 1 | 12,5 |"
        doc = _make_doc(
            "Ein Absatz.", tables=[TableBlock(markdown=table_md, page=1)],
        )
        chunker = MarkdownChunker()
        chunks = chunker.chunk(doc)
        table_chunks = [c for c in chunks if c.is_table]
        assert len(table_chunks) == 1
        assert "|" in table_chunks[0].text

    def test_chunk_index_continuous(self) -> None:
        """chunk_index ist fortlaufend ab 0."""
        body = "## A\n\nText A.\n\n## B\n\nText B.\n\n## C\n\nText C."
        doc = _make_doc(body)
        chunker = MarkdownChunker()
        chunks = chunker.chunk(doc)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_long_section_split_by_sentences(self) -> None:
        """Sehr lange Sections werden an Satzgrenzen aufgeteilt."""
        # Generiere einen langen Text (>768 Tokens)
        sentences = [
            f"Dies ist Satz Nummer {i} mit etwas Inhalt ueber Roboter."
            for i in range(200)
        ]
        long_body = " ".join(sentences)
        doc = _make_doc(long_body)
        chunker = MarkdownChunker()
        chunks = chunker.chunk(doc)
        assert len(chunks) > 1
        # Kein Chunk sollte max_tokens ueberschreiten (mit Toleranz)
        for chunk in chunks:
            tokens = count_tokens(chunk.text)
            assert tokens <= 900, (
                f"Chunk {chunk.chunk_index} hat {tokens} Tokens (max 768+Toleranz)"
            )

    def test_empty_doc(self) -> None:
        """Leeres Dokument ergibt keine Chunks."""
        doc = _make_doc("")
        chunker = MarkdownChunker()
        chunks = chunker.chunk(doc)
        assert len(chunks) == 0

    def test_headings_in_chunk(self) -> None:
        """Chunks enthalten Heading-Informationen."""
        body = "## Technische Daten\n\nDer Roboter hat 6 Achsen."
        doc = _make_doc(body)
        chunker = MarkdownChunker()
        chunks = chunker.chunk(doc)
        assert len(chunks) >= 1
        assert any("Technische Daten" in h for c in chunks for h in c.headings)

    # ── Neue Tests: Tabellen-Splitting ──

    def test_oversized_table_split(self) -> None:
        """Tabellen ueber chunk_max_tokens werden an Zeilengrenzen geteilt."""
        header = "| Spalte A | Spalte B | Spalte C |"
        sep = "|---|---|---|"
        rows = [
            f"| Wert {i} | Beschreibung Nummer {i} fuer den Test | Ergebnis {i * 10} |"
            for i in range(200)
        ]
        table_md = "\n".join([header, sep] + rows)
        doc = _make_doc(
            "Ein Absatz.",
            tables=[TableBlock(markdown=table_md, page=1)],
        )
        chunker = MarkdownChunker()
        chunks = chunker.chunk(doc)
        table_chunks = [c for c in chunks if c.is_table]
        # Muss in mehrere Chunks geteilt werden
        assert len(table_chunks) > 1
        # Jeder Chunk muss Token-Limit respektieren
        for tc in table_chunks:
            tokens = count_tokens(tc.text)
            assert tokens <= 900, (
                f"Table-Chunk {tc.chunk_index} hat {tokens} Tokens"
            )
        # Jeder Sub-Chunk muss den Header enthalten
        for tc in table_chunks:
            assert "Spalte A" in tc.text
            assert "---|" in tc.text

    def test_small_table_stays_whole(self) -> None:
        """Tabellen innerhalb des Token-Limits werden nicht geteilt."""
        table_md = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
        doc = _make_doc(
            "Text.", tables=[TableBlock(markdown=table_md, page=1)],
        )
        chunker = MarkdownChunker()
        chunks = chunker.chunk(doc)
        table_chunks = [c for c in chunks if c.is_table]
        assert len(table_chunks) == 1

    # ── Neue Tests: doc_type-Profile ──

    def test_chunk_accepts_doc_type(self) -> None:
        """chunk() akzeptiert doc_type-Parameter ohne Fehler."""
        doc = _make_doc("## Test\n\nEin Absatz.")
        chunker = MarkdownChunker()
        chunks = chunker.chunk(doc, doc_type="abschlussarbeit")
        assert len(chunks) >= 1

    def test_simple_path_flyer(self) -> None:
        """Kurze Flyer-Dokumente ergeben einen Chunk via simple_path."""
        doc = _make_doc("Ein kurzer Flyer-Text mit wenigen Saetzen.")
        chunker = MarkdownChunker()
        chunks = chunker.chunk(doc, doc_type="flyer")
        assert len(chunks) == 1
