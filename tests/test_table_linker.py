"""Tests fuer die Table-to-Chunk-Verknuepfung."""
from __future__ import annotations

from halle_gehirn.pipeline.chunker import Chunk
from halle_gehirn.pipeline.table_linker import (
    extract_table_number,
    find_table_refs_in_text,
    link_tables_to_chunks,
)


def _make_chunk(
    text: str,
    is_table: bool = False,
    headings: list[str] | None = None,
) -> Chunk:
    """Helfer: Erstellt einen Chunk mit Mindestfeldern."""
    return Chunk(
        text=text,
        char_start=0,
        char_end=len(text),
        chunk_index=0,
        headings=headings or [],
        is_table=is_table,
    )


class TestExtractTableNumber:
    """Tests fuer extract_table_number()."""

    def test_tabelle_N(self) -> None:
        assert extract_table_number("Tabelle 3: Messergebnisse") == 3

    def test_tab_N(self) -> None:
        assert extract_table_number("Tab. 5 - Werte") == 5

    def test_table_N(self) -> None:
        assert extract_table_number("Table 12: Results") == 12

    def test_tafel_N(self) -> None:
        assert extract_table_number("Tafel 1") == 1

    def test_no_number(self) -> None:
        assert extract_table_number("Keine Nummer hier") is None

    def test_none_input(self) -> None:
        assert extract_table_number(None) is None

    def test_empty_string(self) -> None:
        assert extract_table_number("") is None

    def test_case_insensitive(self) -> None:
        assert extract_table_number("TABELLE 7: Daten") == 7


class TestFindTableRefsInText:
    """Tests fuer find_table_refs_in_text()."""

    def test_single_ref(self) -> None:
        text = "Wie in Tabelle 3 dargestellt, sind die Werte hoch."
        assert find_table_refs_in_text(text) == {3}

    def test_multiple_refs(self) -> None:
        text = "Tabelle 1 und Tabelle 2 zeigen die Ergebnisse."
        assert find_table_refs_in_text(text) == {1, 2}

    def test_no_refs(self) -> None:
        text = "Dieser Text referenziert keine Tabelle."
        assert find_table_refs_in_text(text) == set()

    def test_tab_abbreviation(self) -> None:
        text = "Siehe Tab. 5 fuer Details."
        assert find_table_refs_in_text(text) == {5}


class TestLinkTablesToChunks:
    """Tests fuer link_tables_to_chunks()."""

    def test_basic_linking(self) -> None:
        """Tabellen-Chunk wird mit dem referenzierenden Body-Chunk verknuepft."""
        body = _make_chunk(
            "Die Messergebnisse in Tabelle 3 zeigen deutliche Verbesserungen "
            "gegenueber dem Ausgangszustand.",
        )
        table = _make_chunk(
            "| Messung | Wert |\n|---|---|\n| A | 1.5 |",
            is_table=True,
        )
        chunks = [body, table]
        captions = ["Tabelle 3: Messergebnisse"]
        link_tables_to_chunks(chunks, captions)
        assert table.table_caption == "Tabelle 3: Messergebnisse"
        assert table.table_context is not None
        assert "Messergebnisse" in table.table_context

    def test_no_matching_body(self) -> None:
        """Ohne passenden Body-Chunk bleibt table_context None."""
        body = _make_chunk("Text ohne Tabellen-Referenz.")
        table = _make_chunk("| A | B |\n|---|---|", is_table=True)
        chunks = [body, table]
        captions = ["Tabelle 5: Daten"]
        link_tables_to_chunks(chunks, captions)
        assert table.table_caption == "Tabelle 5: Daten"
        assert table.table_context is None

    def test_empty_captions(self) -> None:
        """Leere Captions-Liste aendert nichts."""
        body = _make_chunk("Text.")
        table = _make_chunk("| A |\n|---|\n| 1 |", is_table=True)
        chunks = [body, table]
        link_tables_to_chunks(chunks, [])
        assert table.table_context is None

    def test_context_truncated_at_300_chars(self) -> None:
        """table_context wird auf max. 300 Zeichen gekuerzt."""
        long_text = "Tabelle 1 " + "x" * 500
        body = _make_chunk(long_text)
        table = _make_chunk("| A |\n|---|\n| 1 |", is_table=True)
        chunks = [body, table]
        captions = ["Tabelle 1: Daten"]
        link_tables_to_chunks(chunks, captions)
        assert table.table_context is not None
        assert len(table.table_context) <= 304  # 300 + "..."

    def test_mismatched_count_skips(self) -> None:
        """Unterschiedliche Anzahl Tabellen-Chunks und Captions wird toleriert."""
        table1 = _make_chunk("| A |\n|---|\n| 1 |", is_table=True)
        table2 = _make_chunk("| B |\n|---|\n| 2 |", is_table=True)
        chunks = [table1, table2]
        # Nur eine Caption fuer zwei Tabellen
        captions = ["Tabelle 1: Daten"]
        link_tables_to_chunks(chunks, captions)
        # Mismatch — kein Linking, aber auch kein Crash
        assert table1.table_context is None
        assert table2.table_context is None

    def test_best_body_chunk_selected(self) -> None:
        """Der laengste Body-Chunk mit passender Referenz wird gewaehlt."""
        short_body = _make_chunk("Siehe Tabelle 2.")
        long_body = _make_chunk(
            "In Tabelle 2 sind die ausfuehrlichen Messergebnisse "
            "der zweiten Versuchsreihe dargestellt. Die Daten "
            "zeigen eine signifikante Verbesserung.",
        )
        table = _make_chunk("| M | W |\n|---|---|", is_table=True)
        chunks = [short_body, long_body, table]
        captions = ["Tabelle 2: Ergebnisse"]
        link_tables_to_chunks(chunks, captions)
        assert table.table_context is not None
        assert "ausfuehrlichen" in table.table_context
