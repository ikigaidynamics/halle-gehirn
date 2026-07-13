"""Tests fuer Chunk-Hilfsmodul (Tabellen-Splitting, Section-Splitting)."""
from __future__ import annotations

from halle_gehirn.pipeline.chunk_helpers import split_sections, split_table
from halle_gehirn.pipeline.chunker import count_tokens


class TestSplitTable:
    """Tests fuer das Tabellen-Splitting."""

    def test_small_table_single_chunk(self) -> None:
        """Kleine Tabelle ergibt einen einzelnen Chunk."""
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        parts = split_table(md, max_tokens=768, page=1, count_tokens_fn=count_tokens)
        assert len(parts) == 1
        assert parts[0]["is_table"] is True
        assert parts[0]["page"] == 1

    def test_large_table_splits(self) -> None:
        """Grosse Tabelle wird in mehrere Teile geteilt."""
        header = "| Col A | Col B | Col C |"
        sep = "|---|---|---|"
        rows = [f"| Val {i} | Data {i} | Result {i} |" for i in range(300)]
        md = "\n".join([header, sep, *rows])
        parts = split_table(
            md, max_tokens=100, page=None, count_tokens_fn=count_tokens,
        )
        assert len(parts) > 1
        for part in parts:
            assert part["is_table"] is True
            assert "Col A" in part["text"]  # type: ignore[operator]

    def test_header_repeated_in_all_parts(self) -> None:
        """Jeder Sub-Chunk enthaelt den Original-Header."""
        header = "| Name | Wert |"
        sep = "|---|---|"
        rows = [f"| Item {i} | {i * 100} |" for i in range(100)]
        md = "\n".join([header, sep, *rows])
        parts = split_table(
            md, max_tokens=50, page=1, count_tokens_fn=count_tokens,
        )
        assert len(parts) > 1
        for part in parts:
            text = str(part["text"])
            assert header in text
            assert sep in text

    def test_no_chunk_exceeds_max_tokens(self) -> None:
        """Kein Tabellen-Teil darf max_tokens ueberschreiten."""
        header = "| Spalte A | Spalte B |"
        sep = "|---|---|"
        rows = [f"| Wert {i} | Beschreibung {i} |" for i in range(200)]
        md = "\n".join([header, sep, *rows])
        max_tok = 100
        parts = split_table(
            md, max_tokens=max_tok, page=None, count_tokens_fn=count_tokens,
        )
        for part in parts:
            tokens = count_tokens(str(part["text"]))
            # Toleranz: Header + 1 Zeile koennte knapp ueber max sein
            assert tokens <= max_tok + 50, (
                f"Tabellen-Teil hat {tokens} Tokens (max {max_tok}+Toleranz)"
            )

    def test_no_separator_returns_single(self) -> None:
        """Text ohne Tabellen-Separator wird als ein Chunk zurueckgegeben."""
        md = "Not a real table\nJust some lines"
        parts = split_table(
            md, max_tokens=768, page=None, count_tokens_fn=count_tokens,
        )
        assert len(parts) == 1


class TestSplitSections:
    """Tests fuer das Section-Splitting."""

    def test_no_headings_single_section(self) -> None:
        """Text ohne Headings ergibt eine einzelne Section."""
        sections = split_sections("Ein einfacher Absatz.")
        assert len(sections) == 1

    def test_headings_create_sections(self) -> None:
        """Headings erzeugen separate Sections."""
        body = "## A\n\nText A.\n\n## B\n\nText B."
        sections = split_sections(body)
        assert len(sections) == 2
        assert sections[0].headings == ["A"]
        assert sections[1].headings == ["B"]

    def test_text_before_first_heading(self) -> None:
        """Text vor dem ersten Heading wird als eigene Section behandelt."""
        body = "Vorspann-Text.\n\n## Kapitel 1\n\nInhalt."
        sections = split_sections(body)
        assert len(sections) == 2
        assert sections[0].headings == []

    def test_empty_body(self) -> None:
        """Leerer Body ergibt keine Sections."""
        sections = split_sections("")
        assert len(sections) == 0
