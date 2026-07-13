"""Tests fuer WP2: Contextual-Retrieval-Verdrahtung + Delta-Ingest.

Prueft mit gemocktem Ollama/Qdrant:
- build_doc_summary (Kurzfassung bevorzugt)
- OllamaContextEnricher setzt context_prefix / degradiert graceful
- run_ingest verdrahtet den Enricher (prefix landet in payload.text)
- skip_hashes ueberspringt unveraenderte Dokumente (docs_unchanged)
- delete_stale_chunks / _cleanup_stale (Delta-Hygiene)
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from halle_gehirn.config import Settings
from halle_gehirn.extraction.base import ExtractedDoc
from halle_gehirn.pipeline.chunker import Chunk
from halle_gehirn.pipeline.context_enricher import (
    OllamaContextEnricher,
    build_doc_summary,
)
from halle_gehirn.pipeline.indexer import _cleanup_stale
from halle_gehirn.pipeline.ingest import compute_source_hash, run_ingest
from halle_gehirn.vector_store.qdrant_client import delete_stale_chunks
from halle_gehirn.vector_store.schema import ChunkPayload

# ── Helfer ──


def _make_doc(body: str, title: str = "Testdokument") -> ExtractedDoc:
    """Erstellt ein ExtractedDoc mit gegebenem Body."""
    return ExtractedDoc(
        source="/test/doc.md",
        source_type="manual",
        title=title,
        body_md=body,
    )


def _make_chunks(n: int = 2) -> list[Chunk]:
    """Erstellt n einfache Chunks."""
    return [
        Chunk(
            text=f"Inhalt des Chunks Nummer {i}.",
            char_start=i * 30,
            char_end=i * 30 + 28,
            chunk_index=i,
        )
        for i in range(n)
    ]


def _write_corpus(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Legt Manifest, Vokabular und ein .md-Dokument in tmp_path an.

    Returns:
        (manifest_path, vokabular_path, manual_dir, md_path)
    """
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir()
    md_path = manual_dir / "notiz.md"
    md_path.write_text(
        "## Anlagenbeschreibung\n\n"
        "Der KUKA-Roboter besitzt sechs Achsen und wird in der "
        "Modellfabrik fuer Pick-and-Place-Aufgaben eingesetzt. "
        "Die Wiederholgenauigkeit betraegt 0,05 Millimeter.\n",
        encoding="utf-8",
    )
    manifest = {
        "dokumente": [
            {
                "datei": "notiz.md",
                "titel": "KUKA-Notiz",
                "doc_type": "handbuch",
                "bereich": ["infrastruktur"],
                "herkunft": "lehrstuhl_at",
            },
        ],
    }
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.dump(manifest), encoding="utf-8")
    vokabular_path = tmp_path / "vokabular.yaml"
    vokabular_path.write_text(
        yaml.dump({"thema": {}, "anlage": {}, "projekt": {},
                   "ansprechperson": {}, "autor": {}}),
        encoding="utf-8",
    )
    return manifest_path, vokabular_path, manual_dir, md_path


class _FakeOllamaClient:
    """Gemockter ollama.AsyncClient."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def chat(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        if self.fail:
            raise ConnectionError("Ollama nicht erreichbar")
        return {"message": {"content": "Ein praegnanter Kontextsatz."}}


# ── build_doc_summary ──


class TestBuildDocSummary:
    """Tests fuer die Dokument-Zusammenfassung des Kontext-Prompts."""

    def test_prefers_kurzfassung_section(self) -> None:
        """Kurzfassungs-Abschnitt wird dem Dokumentanfang vorgezogen."""
        body = (
            "# Titelblatt\n\nBTU Cottbus, Fakultaet 3.\n\n"
            "## Kurzfassung\n\nDiese Arbeit optimiert die Bahnplanung.\n\n"
            "## 1 Einleitung\n\nText."
        )
        summary = build_doc_summary(body)
        assert summary.startswith("## Kurzfassung")
        assert "Bahnplanung" in summary

    def test_fallback_to_document_head(self) -> None:
        """Ohne Kurzfassung wird der Dokumentanfang genommen."""
        body = "## Einleitung\n\nEin Dokument ohne Kurzfassung." + "x" * 2000
        summary = build_doc_summary(body)
        assert summary.startswith("## Einleitung")
        assert len(summary) <= 800

    def test_numbered_zusammenfassung_not_matched(self) -> None:
        """Nummeriertes '## 7 Zusammenfassung' zaehlt nicht als Kurzfassung."""
        body = "Anfang des Dokuments.\n\n## 7 Zusammenfassung\n\nFazit."
        summary = build_doc_summary(body)
        assert summary.startswith("Anfang des Dokuments.")


# ── Enricher ──


class TestOllamaContextEnricher:
    """Tests fuer den Enricher (gemockter Ollama-Client)."""

    def _enricher(self, fail: bool = False) -> OllamaContextEnricher:
        settings = Settings(use_contextual_retrieval=True)
        enricher = OllamaContextEnricher(settings=settings)
        enricher._client = _FakeOllamaClient(fail=fail)  # type: ignore[assignment]
        return enricher

    def test_enrich_sets_context_prefix(self) -> None:
        """Erfolgreicher Lauf setzt context_prefix auf allen Chunks."""
        chunks = _make_chunks(3)
        doc = _make_doc("## Abschnitt\n\nInhalt.")
        result = asyncio.run(self._enricher().enrich(chunks, doc))
        assert all(
            c.context_prefix == "Ein praegnanter Kontextsatz." for c in result
        )

    def test_enrich_graceful_when_ollama_down(self) -> None:
        """Ollama-Ausfall: kein Crash, Prefixe bleiben None."""
        chunks = _make_chunks(3)
        doc = _make_doc("## Abschnitt\n\nInhalt.")
        result = asyncio.run(self._enricher(fail=True).enrich(chunks, doc))
        assert all(c.context_prefix is None for c in result)

    def test_enrich_disabled_via_settings(self) -> None:
        """use_contextual_retrieval=false ueberspringt das Enrichment."""
        settings = Settings(use_contextual_retrieval=False)
        enricher = OllamaContextEnricher(settings=settings)
        client = _FakeOllamaClient()
        enricher._client = client  # type: ignore[assignment]
        chunks = _make_chunks(2)
        asyncio.run(enricher.enrich(chunks, _make_doc("Text.")))
        assert client.calls == 0
        assert all(c.context_prefix is None for c in chunks)


# ── run_ingest-Verdrahtung ──


class _FakeEnricher:
    """Protocol-konformer Fake-Enricher fuer run_ingest-Tests."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings

    async def enrich(
        self, chunks: list[Chunk], doc: ExtractedDoc,
    ) -> list[Chunk]:
        for chunk in chunks:
            chunk.context_prefix = f"Kontext aus {doc.title}."
        return chunks


class _BrokenEnricher(_FakeEnricher):
    """Enricher, der komplett fehlschlaegt (Degradations-Test)."""

    async def enrich(
        self, chunks: list[Chunk], doc: ExtractedDoc,
    ) -> list[Chunk]:
        raise ConnectionError("Ollama nicht erreichbar")


class TestRunIngestEnrichment:
    """run_ingest ruft den Enricher auf und baut Prefixe in payload.text."""

    def test_prefix_lands_in_payload_text(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """context_prefix wird vor text_raw in payload.text gestellt."""
        manifest, vokabular, manual, _ = _write_corpus(tmp_path)
        monkeypatch.setattr(
            "halle_gehirn.pipeline.ingest.OllamaContextEnricher",
            _FakeEnricher,
        )
        settings = Settings(use_contextual_retrieval=True)
        payloads, stats = run_ingest(
            manifest_path=manifest,
            vokabular_path=vokabular,
            manual_dir=manual,
            settings=settings,
        )
        assert stats.docs_success == 1
        assert payloads
        for p in payloads:
            assert p.context_prefix == "Kontext aus KUKA-Notiz."
            assert p.text.startswith("Kontext aus KUKA-Notiz.")
            assert p.text_raw in p.text
            assert p.text != p.text_raw

    def test_degrades_without_prefix_on_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Enricher-Totalausfall: Ingest laeuft weiter, Prefixe None."""
        manifest, vokabular, manual, _ = _write_corpus(tmp_path)
        monkeypatch.setattr(
            "halle_gehirn.pipeline.ingest.OllamaContextEnricher",
            _BrokenEnricher,
        )
        settings = Settings(use_contextual_retrieval=True)
        payloads, stats = run_ingest(
            manifest_path=manifest,
            vokabular_path=vokabular,
            manual_dir=manual,
            settings=settings,
        )
        assert stats.docs_success == 1
        assert stats.docs_failed == 0
        assert payloads
        for p in payloads:
            assert p.context_prefix is None
            assert p.text == p.text_raw

    def test_disabled_skips_enricher(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """use_contextual_retrieval=false instanziiert keinen Enricher."""
        manifest, vokabular, manual, _ = _write_corpus(tmp_path)

        def _boom(*_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("Enricher darf nicht gebaut werden")

        monkeypatch.setattr(
            "halle_gehirn.pipeline.ingest.OllamaContextEnricher", _boom,
        )
        settings = Settings(use_contextual_retrieval=False)
        payloads, stats = run_ingest(
            manifest_path=manifest,
            vokabular_path=vokabular,
            manual_dir=manual,
            settings=settings,
        )
        assert stats.docs_success == 1
        assert all(p.context_prefix is None for p in payloads)


# ── Delta-Ingest ──


class TestDeltaIngest:
    """skip_hashes ueberspringt unveraenderte Dokumente."""

    def test_unchanged_doc_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Dokument mit bekanntem Hash wird nicht erneut verarbeitet."""
        manifest, vokabular, manual, md_path = _write_corpus(tmp_path)
        monkeypatch.setattr(
            "halle_gehirn.pipeline.ingest.OllamaContextEnricher",
            _FakeEnricher,
        )
        known_hash = compute_source_hash(md_path)
        settings = Settings(use_contextual_retrieval=True)
        payloads, stats = run_ingest(
            manifest_path=manifest,
            vokabular_path=vokabular,
            manual_dir=manual,
            settings=settings,
            skip_hashes={known_hash},
        )
        assert stats.docs_unchanged == 1
        assert stats.docs_success == 0
        assert payloads == []

    def test_changed_doc_processed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Unbekannter Hash → Dokument wird normal verarbeitet."""
        manifest, vokabular, manual, _ = _write_corpus(tmp_path)
        monkeypatch.setattr(
            "halle_gehirn.pipeline.ingest.OllamaContextEnricher",
            _FakeEnricher,
        )
        settings = Settings(use_contextual_retrieval=True)
        payloads, stats = run_ingest(
            manifest_path=manifest,
            vokabular_path=vokabular,
            manual_dir=manual,
            settings=settings,
            skip_hashes={"anderer-hash"},
        )
        assert stats.docs_unchanged == 0
        assert stats.docs_success == 1
        assert payloads


# ── Stale-Delete ──


class _FakeQdrantClient:
    """Minimaler Qdrant-Client-Stub fuer delete_stale_chunks."""

    def __init__(self, stale_count: int) -> None:
        self.stale_count = stale_count
        self.deleted_filters: list[Any] = []

    def collection_exists(self, _name: str) -> bool:
        return True

    def count(self, **_kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(count=self.stale_count)

    def delete(self, **kwargs: Any) -> None:
        self.deleted_filters.append(kwargs["points_selector"])


class TestStaleDelete:
    """Tests fuer delete_stale_chunks und _cleanup_stale."""

    def test_deletes_when_stale_exists(self) -> None:
        """Stale-Punkte vorhanden → delete wird aufgerufen."""
        fake = _FakeQdrantClient(stale_count=7)
        deleted = delete_stale_chunks(
            "notiz.md", "hash-neu", 5,
            client=fake,  # type: ignore[arg-type]
        )
        assert deleted == 7
        assert len(fake.deleted_filters) == 1

    def test_no_delete_when_clean(self) -> None:
        """Keine Stale-Punkte → kein delete-Aufruf."""
        fake = _FakeQdrantClient(stale_count=0)
        deleted = delete_stale_chunks(
            "notiz.md", "hash-neu", 5,
            client=fake,  # type: ignore[arg-type]
        )
        assert deleted == 0
        assert fake.deleted_filters == []

    def test_cleanup_stale_groups_by_document(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """_cleanup_stale ruft delete je (datei, hash) mit max Index+1."""
        calls: list[tuple[str, str, int]] = []

        def _fake_delete(datei: str, h: str, count: int) -> int:
            calls.append((datei, h, count))
            return 2

        monkeypatch.setattr(
            "halle_gehirn.pipeline.indexer.delete_stale_chunks",
            _fake_delete,
        )
        payloads = [
            _payload("a.md", "hash-a", 0),
            _payload("a.md", "hash-a", 1),
            _payload("b.md", "hash-b", 0),
        ]
        total = _cleanup_stale(payloads)
        assert total == 4
        assert ("a.md", "hash-a", 2) in calls
        assert ("b.md", "hash-b", 1) in calls


def _payload(datei: str, source_hash: str, chunk_index: int) -> ChunkPayload:
    """Minimales ChunkPayload fuer Indexer-Tests."""
    return ChunkPayload(
        text="Text.",
        text_raw="Text.",
        source_type="manual",
        chunk_index=chunk_index,
        char_start=0,
        char_end=5,
        ingested_at="2026-07-13T00:00:00+00:00",
        source_hash=source_hash,
        titel="T",
        datei=datei,
        doc_type="handbuch",  # type: ignore[arg-type]
        bereich=["infrastruktur"],  # type: ignore[list-item]
        quelltyp="primaer",  # type: ignore[arg-type]
        herkunft="lehrstuhl_at",  # type: ignore[arg-type]
        vertraulichkeit="intern",  # type: ignore[arg-type]
        status="final",  # type: ignore[arg-type]
    )
