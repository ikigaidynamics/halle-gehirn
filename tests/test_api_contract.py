"""Tests fuer WP6: API-Vertrag, Snippet-Kuerzung, Fundstellen im Prompt.

- /chat und /chat/stream liefern dieselben Quellen-Felder
  (Source-Schema == _build_sources-Keys)
- Snippets werden serverseitig gekuerzt
- format_context gibt Seite + Breadcrumb an das LLM
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from halle_gehirn.api.schemas import Source
from halle_gehirn.generator.prompts import format_context
from halle_gehirn.pipeline.orchestrator import (
    _build_sources,
    _truncate_snippet,
)


@dataclass
class FakeHit:
    """Simuliert einen RetrievalHit mit vollem Payload."""

    point_id: str = "abc123"
    score: float = 0.8
    rerank_score: float = 0.85
    payload: dict[str, Any] = field(default_factory=lambda: {
        "text": "Kontextsatz.\n\nDer UR10e hat eine Nutzlast von 10 kg.",
        "text_raw": "Der UR10e hat eine Nutzlast von 10 kg.",
        "titel": "UR10e Datenblatt",
        "source_url": None,
        "datei": "anlagen/ur10e.pdf",
        "page": 12,
        "doc_type": "anlagendoku",
        "breadcrumb": "Technische Daten > Nutzlast",
    })


class TestSourceContract:
    """Source-Schema und _build_sources muessen deckungsgleich sein."""

    def test_build_sources_keys_match_schema(self) -> None:
        """Jeder _build_sources-Key existiert im Source-Schema —
        /chat (Pydantic) verliert damit keine Felder mehr gegenueber
        /chat/stream (raw dict)."""
        sources = _build_sources([FakeHit()])
        schema_fields = set(Source.model_fields.keys())
        for src in sources:
            assert set(src.keys()) == schema_fields, (
                f"Vertrags-Drift: dict={sorted(src.keys())} "
                f"schema={sorted(schema_fields)}"
            )

    def test_roundtrip_keeps_all_fields(self) -> None:
        """Source(**dict) behaelt datei/doc_type/breadcrumb/page."""
        src_dict = _build_sources([FakeHit()])[0]
        src = Source(**src_dict)
        assert src.datei == "anlagen/ur10e.pdf"
        assert src.doc_type == "anlagendoku"
        assert src.breadcrumb == "Technische Daten > Nutzlast"
        assert src.page == 12

    def test_none_payload_values_coerced(self) -> None:
        """None-Werte im Payload brechen das Schema nicht."""
        hit = FakeHit(payload={
            "text_raw": "Text.",
            "titel": None,
            "breadcrumb": None,
            "doc_type": None,
            "datei": None,
        })
        src = Source(**_build_sources([hit])[0])
        assert src.titel == "Unbekannt"
        assert src.breadcrumb == ""


class TestSnippetTruncation:
    """Snippets werden serverseitig auf ~300 Zeichen gekuerzt."""

    def test_long_snippet_truncated_at_word_boundary(self) -> None:
        """Lange Chunks kommen gekuerzt mit Ellipse an."""
        long_text = "Wort " * 200
        hit = FakeHit(payload={"text_raw": long_text, "titel": "T"})
        snippet = _build_sources([hit])[0]["snippet"]
        assert len(snippet) <= 310
        assert snippet.endswith("…")

    def test_short_snippet_unchanged(self) -> None:
        """Kurze Snippets bleiben unveraendert."""
        assert _truncate_snippet("Kurzer Text.") == "Kurzer Text."


class TestFormatContextLocation:
    """format_context reicht Seite + Kapitel an das LLM durch."""

    def test_page_and_breadcrumb_in_context(self) -> None:
        """Quellen-Block enthaelt (S. 12 · Breadcrumb)."""
        context = format_context([FakeHit()])
        assert "[S1] UR10e Datenblatt (S. 12 · Technische Daten > Nutzlast)" in context
        assert "Nutzlast von 10 kg" in context

    def test_no_location_without_page_and_breadcrumb(self) -> None:
        """Ohne Seite/Breadcrumb kein leerer Klammer-Zusatz."""
        hit = FakeHit(payload={"text": "Text.", "titel": "Doc"})
        context = format_context([hit])
        assert context.startswith("[S1] Doc\n")
        assert "()" not in context

    def test_page_only(self) -> None:
        """Nur Seite vorhanden → (S. 3)."""
        hit = FakeHit(payload={"text": "T.", "titel": "Doc", "page": 3})
        assert "[S1] Doc (S. 3)" in format_context([hit])
