"""Tests fuer die Bild-Integration (Linker, Payload, Serve-Parse, Erasure)."""
from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from halle_gehirn.extraction.base import FigureBlock
from halle_gehirn.extraction.figure_utils import (
    _decode_data_uri,
    extract_figures_from_serve,
    save_figures,
)
from halle_gehirn.pipeline.chunker import Chunk
from halle_gehirn.pipeline.figure_linker import (
    extract_figure_number,
    find_figure_refs_in_text,
    link_figures_to_chunks,
)
from halle_gehirn.pipeline.ingest import ManifestEntry, build_chunk_payload

# ── Figure Linker: Caption-Regex ──


class TestExtractFigureNumber:
    """extract_figure_number erkennt DE/EN-Varianten."""

    @pytest.mark.parametrize(
        ("caption", "expected"),
        [
            ("Abbildung 3: Systemarchitektur", 3),
            ("Abb. 12 - Uebersicht", 12),
            ("Abb 7: Detail", 7),
            ("Bild 1: Foto", 1),
            ("Figure 5: Overview", 5),
            ("Fig. 10 - Layout", 10),
            ("Fig 99: Schema", 99),
        ],
    )
    def test_known_patterns(self, caption: str, expected: int) -> None:
        assert extract_figure_number(caption) == expected

    def test_no_number(self) -> None:
        assert extract_figure_number("Ohne Nummer") is None

    def test_none_caption(self) -> None:
        assert extract_figure_number(None) is None

    def test_case_insensitive(self) -> None:
        assert extract_figure_number("ABBILDUNG 42: Test") == 42


class TestFindFigureRefsInText:
    """find_figure_refs_in_text findet alle Referenzen im Chunk-Text."""

    def test_multiple_refs(self) -> None:
        text = "Siehe Abbildung 3 und Abb. 7 fuer Details. Auch Fig. 3 nochmal."
        refs = find_figure_refs_in_text(text)
        assert refs == {3, 7}

    def test_no_refs(self) -> None:
        assert find_figure_refs_in_text("Kein Verweis hier.") == set()


# ── Figure Linker: Linking ──


def _make_chunk(text: str, page: int | None = None) -> Chunk:
    return Chunk(
        text=text, char_start=0, char_end=len(text),
        chunk_index=0, page=page,
    )


def _make_figure(
    caption: str | None = None, page: int | None = None, path: str = "h/fig.png",
) -> FigureBlock:
    return FigureBlock(image_path=path, page=page, caption=caption)


class TestLinkFiguresToChunks:
    """link_figures_to_chunks verknuepft Bilder mit Chunks."""

    def test_link_by_number(self) -> None:
        """Primaer: Abbildungsnummer im Text matcht Caption-Nummer."""
        chunk = _make_chunk("Siehe Abbildung 3 fuer Details.", page=1)
        fig = _make_figure(caption="Abbildung 3: Architektur", page=2)
        link_figures_to_chunks([chunk], [fig])
        assert chunk.figure_refs == ["h/fig.png"]
        assert chunk.figure_captions == ["Abbildung 3: Architektur"]

    def test_fallback_by_page(self) -> None:
        """Fallback: Figur ohne Nummer-Match geht an gleiche Seite."""
        chunk = _make_chunk("Text ohne Verweis.", page=5)
        fig = _make_figure(caption=None, page=5, path="h/img.png")
        link_figures_to_chunks([chunk], [fig])
        assert chunk.figure_refs == ["h/img.png"]

    def test_no_match(self) -> None:
        """Kein Match: Chunk bleibt ohne Bilder."""
        chunk = _make_chunk("Text.", page=1)
        fig = _make_figure(caption="Abbildung 9: Anderes", page=99)
        link_figures_to_chunks([chunk], [fig])
        assert chunk.figure_refs == []

    def test_deduplication(self) -> None:
        """Gleiche Figur wird nicht doppelt angehaengt."""
        chunk = _make_chunk("Abbildung 1 hier. Und nochmal Abb. 1.", page=1)
        fig = _make_figure(caption="Abbildung 1: X", page=1, path="h/f.png")
        link_figures_to_chunks([chunk], [fig])
        assert chunk.figure_refs == ["h/f.png"]

    def test_empty_figures_list(self) -> None:
        """Leere Figures-Liste ist ein No-Op."""
        chunk = _make_chunk("Text.")
        link_figures_to_chunks([chunk], [])
        assert chunk.figure_refs == []


# ── Payload: figure_refs + caption-fold ──


class TestBuildChunkPayloadFigures:
    """build_chunk_payload integriert Abbildungsdaten."""

    def _entry(self) -> ManifestEntry:
        return ManifestEntry(
            datei="test.pdf", titel="Test", doc_type="handbuch",
            bereich=["forschung"], herkunft="lehrstuhl_at",
        )

    def test_figure_fields_in_payload(self) -> None:
        """figure_refs und figure_captions landen im Payload."""
        chunk = _make_chunk("Text mit Abbildung 1.")
        chunk.figure_refs = ["abc123/fig_000.png"]
        chunk.figure_captions = ["Abbildung 1: Schema"]
        payload = build_chunk_payload(chunk, self._entry(), "abc123", "test.pdf")
        assert payload.figure_refs == ["abc123/fig_000.png"]
        assert payload.figure_captions == ["Abbildung 1: Schema"]

    def test_caption_folded_into_text(self) -> None:
        """Captions werden an text (nicht text_raw) angehaengt."""
        chunk = _make_chunk("Haupttext.")
        chunk.figure_captions = ["Abbildung 1: Schema"]
        payload = build_chunk_payload(chunk, self._entry(), "h", "t.pdf")
        assert "Abbildung 1: Schema" in payload.text
        assert "Abbildung 1: Schema" not in payload.text_raw

    def test_no_figures_no_change(self) -> None:
        """Ohne Bilder bleibt text == text_raw (kein Suffix)."""
        chunk = _make_chunk("Nur Text.")
        payload = build_chunk_payload(chunk, self._entry(), "h", "t.pdf")
        assert payload.text == "Nur Text."
        assert payload.text_raw == "Nur Text."
        assert payload.figure_refs == []
        assert payload.figure_captions == []


# ── Serve: Base64-Parsing ──


class TestDecodeDataUri:
    """_decode_data_uri dekodiert data:image URIs."""

    def test_valid_png(self) -> None:
        raw = b"\x89PNG\r\n\x1a\n"
        uri = f"data:image/png;base64,{base64.b64encode(raw).decode()}"
        result = _decode_data_uri(uri)
        assert result == raw

    def test_invalid_uri(self) -> None:
        assert _decode_data_uri("not-a-data-uri") is None


class TestSaveFigures:
    """save_figures schreibt Bilder und erzeugt FigureBlocks."""

    def test_saves_to_disk(self, tmp_path: Path) -> None:
        settings = MagicMock()
        settings.figures_dir = str(tmp_path)
        items = [{"image_bytes": b"\x89PNG", "page": 1, "caption": "C", "fig_index": 0}]
        blocks = save_figures(items, "abcdef1234567890", settings)
        assert len(blocks) == 1
        assert blocks[0].image_path == "abcdef1234567890/fig_000.png"
        assert (tmp_path / "abcdef1234567890" / "fig_000.png").exists()

    def test_empty_input(self) -> None:
        assert save_figures([], "h", MagicMock()) == []


class TestExtractFiguresFromServe:
    """extract_figures_from_serve parst Base64-Bilder aus json_content."""

    def test_parses_pictures(self, tmp_path: Path) -> None:
        raw_bytes = b"\x89PNG\r\n"
        b64 = base64.b64encode(raw_bytes).decode()
        jc = {
            "pictures": [
                {
                    "image": {"uri": f"data:image/png;base64,{b64}"},
                    "prov": [{"page_no": 3}],
                    "captions": [],
                },
            ],
        }
        settings = MagicMock()
        settings.figures_dir = str(tmp_path)
        blocks = extract_figures_from_serve(jc, "hash16chars00000", settings)
        assert len(blocks) == 1
        assert blocks[0].page == 3
        assert (tmp_path / "hash16chars00000" / "fig_000.png").exists()


# ── Erasure: Figures-Verzeichnis ──


class TestErasureFigures:
    """delete_by_source_hash entfernt auch das Figures-Verzeichnis."""

    def test_figures_dir_removed(self, tmp_path: Path) -> None:
        """Verzeichnis wird geloescht wenn vorhanden."""
        fig_dir = tmp_path / "abcdef1234567890"
        fig_dir.mkdir()
        (fig_dir / "fig_000.png").write_bytes(b"\x89PNG")

        mock_client = MagicMock()
        mock_settings = MagicMock()
        mock_settings.qdrant_collection = "test"
        mock_settings.figures_dir = str(tmp_path)

        with (
            patch("halle_gehirn.vector_store.qdrant_client.get_qdrant_client", return_value=mock_client),
            patch("halle_gehirn.vector_store.qdrant_client.get_settings", return_value=mock_settings),
        ):
            from halle_gehirn.vector_store.qdrant_client import delete_by_source_hash
            # source_hash[:16] == "abcdef1234567890"
            delete_by_source_hash("abcdef1234567890" + "0" * 48, client=mock_client)

        assert not fig_dir.exists()

    def test_no_figures_dir_no_error(self, tmp_path: Path) -> None:
        """Fehlendes Verzeichnis ist kein Fehler."""
        mock_client = MagicMock()
        mock_settings = MagicMock()
        mock_settings.qdrant_collection = "test"
        mock_settings.figures_dir = str(tmp_path)

        with (
            patch("halle_gehirn.vector_store.qdrant_client.get_qdrant_client", return_value=mock_client),
            patch("halle_gehirn.vector_store.qdrant_client.get_settings", return_value=mock_settings),
        ):
            from halle_gehirn.vector_store.qdrant_client import delete_by_source_hash
            delete_by_source_hash("nonexistent" + "0" * 53, client=mock_client)
        # No exception raised
