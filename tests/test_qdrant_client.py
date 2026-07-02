"""Tests fuer vector_store/qdrant_client.py gegen echtes Qdrant.

Voraussetzung: Qdrant laeuft auf QDRANT_URL (Default: http://localhost:6335).
Tests verwenden eine dedizierte Test-Collection, um Produktions-Daten nicht zu
beruehren.
"""
from __future__ import annotations

import pytest
from qdrant_client import QdrantClient

from halle_gehirn.config import Settings
from halle_gehirn.pipeline.ingest import deterministic_chunk_id
from halle_gehirn.vector_store.qdrant_client import (
    QdrantError,
    RetrievalHit,
    _build_filter,
    _build_points,
    delete_by_source_hash,
    ensure_collection,
    hybrid_query,
    reset_collection,
    upsert_chunks,
)
from halle_gehirn.vector_store.schema import (
    Bereich,
    ChunkPayload,
    DocType,
    Herkunft,
    Quelltyp,
    Status,
    Thema,
    Vertraulichkeit,
    create_collection_if_missing,
)

# Test-Collection, um Produktions-Daten nicht zu beruehren
_TEST_COLLECTION = "halle_wissen_test"
_QDRANT_URL = "http://localhost:6335"


def _is_qdrant_available() -> bool:
    """Prueft ob Qdrant erreichbar ist."""
    try:
        client = QdrantClient(url=_QDRANT_URL, timeout=5)
        client.get_collections()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _is_qdrant_available(),
    reason="Qdrant nicht erreichbar",
)


def _test_settings() -> Settings:
    """Settings mit Test-Collection."""
    return Settings(
        qdrant_url=_QDRANT_URL,
        qdrant_collection=_TEST_COLLECTION,
        embedding_dim=8,
    )


def _test_client() -> QdrantClient:
    """Eigener Client fuer Tests."""
    return QdrantClient(url=_QDRANT_URL, timeout=60)


def _make_payload(
    source_hash: str = "abc123",
    chunk_index: int = 0,
    text: str = "Der UR10e ist ein Roboterarm.",
) -> ChunkPayload:
    """Erzeugt ein minimales Test-ChunkPayload."""
    return ChunkPayload(
        text=text,
        text_raw=text,
        source_type="pdf",
        chunk_index=chunk_index,
        char_start=0,
        char_end=len(text),
        ingested_at="2024-01-01T00:00:00+00:00",
        source_hash=source_hash,
        titel="Testdokument",
        doc_type=DocType.ANLAGENDOKU,
        bereich=[Bereich.INFRASTRUKTUR],
        quelltyp=Quelltyp.PRIMAER,
        herkunft=Herkunft.LEHRSTUHL_AT,
        thema=[Thema.MRK],
    )


class _FakeSparse:
    """Simuliert ein fastembed-Sparse-Objekt."""

    def __init__(self, indices: list[int], values: list[float]) -> None:
        self.indices = indices
        self.values = values


@pytest.fixture(autouse=True)
def _clean_test_collection() -> None:  # type: ignore[misc]
    """Erstellt/bereinigt die Test-Collection vor jedem Test."""
    client = _test_client()
    settings = _test_settings()
    if client.collection_exists(settings.qdrant_collection):
        client.delete_collection(settings.qdrant_collection)
    # Monkey-patch get_settings fuer Tests
    import halle_gehirn.vector_store.schema as schema_mod
    import halle_gehirn.vector_store.qdrant_client as client_mod
    original_get = schema_mod.get_settings
    client_original = client_mod.get_settings
    schema_mod.get_settings = _test_settings  # type: ignore[assignment]
    client_mod.get_settings = _test_settings  # type: ignore[assignment]
    # Patch lru_cache fuer get_qdrant_client
    client_mod.get_qdrant_client.cache_clear()
    yield
    # Cleanup
    if client.collection_exists(settings.qdrant_collection):
        client.delete_collection(settings.qdrant_collection)
    schema_mod.get_settings = original_get  # type: ignore[assignment]
    client_mod.get_settings = client_original  # type: ignore[assignment]
    client_mod.get_qdrant_client.cache_clear()


class TestCollectionSetup:
    """Tests fuer Collection-Erstellung."""

    def test_ensure_collection_creates(self) -> None:
        """ensure_collection erstellt die Collection idempotent."""
        client = _test_client()
        assert not client.collection_exists(_TEST_COLLECTION)
        ensure_collection(client)
        assert client.collection_exists(_TEST_COLLECTION)

    def test_ensure_collection_idempotent(self) -> None:
        """Zweimaliger Aufruf veraendert nichts."""
        client = _test_client()
        ensure_collection(client)
        ensure_collection(client)
        assert client.collection_exists(_TEST_COLLECTION)

    def test_reset_collection_recreates(self) -> None:
        """reset_collection loescht und erstellt neu."""
        client = _test_client()
        ensure_collection(client)
        # Upsert einen Punkt
        payload = _make_payload()
        dense = [0.1] * 8
        sparse = _FakeSparse([0, 1], [0.5, 0.3])
        upsert_chunks([payload], [dense], [sparse], client=client)
        info = client.get_collection(_TEST_COLLECTION)
        assert info.points_count > 0
        # Reset
        reset_collection(client)
        info = client.get_collection(_TEST_COLLECTION)
        assert info.points_count == 0

    def test_reset_only_touches_configured_collection(self) -> None:
        """reset_collection darf NUR die konfigurierte Collection loeschen."""
        client = _test_client()
        # Existierende Collections vor Reset
        before = {c.name for c in client.get_collections().collections}
        ensure_collection(client)
        reset_collection(client)
        after = {c.name for c in client.get_collections().collections}
        # Alle vorherigen Collections muessen noch da sein
        assert before.issubset(after)


class TestUpsertAndRetrieve:
    """Tests fuer Upsert mit Named Vectors."""

    def test_upsert_single_chunk(self) -> None:
        """Einzelner Chunk wird korrekt upserted."""
        client = _test_client()
        ensure_collection(client)
        payload = _make_payload()
        dense = [0.1] * 8
        sparse = _FakeSparse([0, 1, 2], [0.5, 0.3, 0.1])
        total = upsert_chunks([payload], [dense], [sparse], client=client)
        assert total == 1
        info = client.get_collection(_TEST_COLLECTION)
        assert info.points_count == 1

    def test_upsert_deterministic_ids(self) -> None:
        """Doppeltes Upsert ueberschreibt (gleiche ID)."""
        client = _test_client()
        ensure_collection(client)
        payload = _make_payload()
        dense = [0.1] * 8
        sparse = _FakeSparse([0], [1.0])
        upsert_chunks([payload], [dense], [sparse], client=client)
        upsert_chunks([payload], [dense], [sparse], client=client)
        info = client.get_collection(_TEST_COLLECTION)
        assert info.points_count == 1

    def test_upsert_multiple_chunks(self) -> None:
        """Mehrere Chunks werden korrekt upserted."""
        client = _test_client()
        ensure_collection(client)
        payloads = [_make_payload(chunk_index=i) for i in range(5)]
        denses = [[0.1 * (i + 1)] * 8 for i in range(5)]
        sparses = [_FakeSparse([0], [1.0]) for _ in range(5)]
        total = upsert_chunks(payloads, denses, sparses, client=client)
        assert total == 5

    def test_upsert_length_mismatch_raises(self) -> None:
        """Ungleiche Laengen loesen QdrantError aus."""
        client = _test_client()
        ensure_collection(client)
        payload = _make_payload()
        with pytest.raises(QdrantError, match="Laengen-Mismatch"):
            upsert_chunks([payload], [], [_FakeSparse([0], [1.0])], client=client)

    def test_upsert_preserves_payload(self) -> None:
        """Payload-Felder sind nach Upsert abrufbar."""
        client = _test_client()
        ensure_collection(client)
        payload = _make_payload(text="Spezifischer Text fuer Retrieval.")
        dense = [0.5] * 8
        sparse = _FakeSparse([0, 1], [0.5, 0.3])
        upsert_chunks([payload], [dense], [sparse], client=client)
        # Direkt per Scroll abrufen
        result = client.scroll(
            collection_name=_TEST_COLLECTION, limit=1, with_payload=True,
        )
        points = result[0]
        assert len(points) == 1
        assert points[0].payload["text"] == "Spezifischer Text fuer Retrieval."
        assert points[0].payload["titel"] == "Testdokument"
        assert points[0].payload["doc_type"] == "anlagendoku"
        assert points[0].payload["source_hash"] == "abc123"


class TestHybridQuery:
    """Tests fuer Hybrid-Query (Fusion)."""

    def test_hybrid_query_returns_hits(self) -> None:
        """Hybrid-Query liefert fusionierte Treffer."""
        client = _test_client()
        ensure_collection(client)
        payloads = [
            _make_payload(chunk_index=0, text="Der UR10e Roboterarm"),
            _make_payload(chunk_index=1, text="Sicherheitshinweise Roboter"),
            _make_payload(chunk_index=2, text="Technische Daten UR10e"),
        ]
        denses = [
            [0.9, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.1, 0.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.8, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        ]
        sparses = [
            _FakeSparse([0, 1], [0.8, 0.2]),
            _FakeSparse([2, 3], [0.7, 0.3]),
            _FakeSparse([0, 4], [0.6, 0.4]),
        ]
        upsert_chunks(payloads, denses, sparses, client=client)
        # Query aehnlich zu chunk 0
        query_dense = [0.85, 0.15, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        query_sparse = _FakeSparse([0, 1], [0.9, 0.1])
        hits = hybrid_query(
            query_dense, query_sparse, limit=3, client=client,
        )
        assert len(hits) > 0
        assert all(isinstance(h, RetrievalHit) for h in hits)
        assert all(isinstance(h.score, float) for h in hits)
        # Bester Treffer sollte chunk 0 oder 2 sein (aehnlichster Dense)
        top_texts = [h.payload.get("text", "") for h in hits[:2]]
        assert any("UR10e" in t for t in top_texts)

    def test_hybrid_query_with_filter(self) -> None:
        """Hybrid-Query respektiert Payload-Filter."""
        client = _test_client()
        ensure_collection(client)
        p1 = _make_payload(chunk_index=0, source_hash="hash_a")
        p2 = _make_payload(chunk_index=0, source_hash="hash_b")
        dense = [0.5] * 8
        sparse = _FakeSparse([0], [1.0])
        upsert_chunks([p1, p2], [dense, dense], [sparse, sparse], client=client)
        query_dense = [0.5] * 8
        query_sparse = _FakeSparse([0], [1.0])
        hits = hybrid_query(
            query_dense, query_sparse, limit=10,
            filters={"source_hash": "hash_a"},
            client=client,
        )
        assert len(hits) == 1
        assert hits[0].payload["source_hash"] == "hash_a"

    def test_hybrid_query_empty_collection(self) -> None:
        """Hybrid-Query auf leerer Collection gibt leere Liste."""
        client = _test_client()
        ensure_collection(client)
        query_dense = [0.5] * 8
        query_sparse = _FakeSparse([0], [1.0])
        hits = hybrid_query(
            query_dense, query_sparse, limit=5, client=client,
        )
        assert hits == []


class TestDeleteBySourceHash:
    """Tests fuer Right-to-Erasure."""

    def test_delete_removes_matching_points(self) -> None:
        """delete_by_source_hash entfernt nur betroffene Punkte."""
        client = _test_client()
        ensure_collection(client)
        p_keep = _make_payload(source_hash="keep_hash", chunk_index=0)
        p_del_0 = _make_payload(source_hash="del_hash", chunk_index=0)
        p_del_1 = _make_payload(source_hash="del_hash", chunk_index=1)
        dense = [0.5] * 8
        sparse = _FakeSparse([0], [1.0])
        upsert_chunks(
            [p_keep, p_del_0, p_del_1],
            [dense] * 3,
            [sparse] * 3,
            client=client,
        )
        info = client.get_collection(_TEST_COLLECTION)
        assert info.points_count == 3
        delete_by_source_hash("del_hash", client=client)
        info = client.get_collection(_TEST_COLLECTION)
        assert info.points_count == 1
        # Verbliebener Punkt ist keep_hash
        result = client.scroll(
            collection_name=_TEST_COLLECTION, limit=10, with_payload=True,
        )
        assert result[0][0].payload["source_hash"] == "keep_hash"

    def test_delete_nonexistent_hash_noop(self) -> None:
        """Loeschen eines nicht vorhandenen Hashs ist ein No-Op."""
        client = _test_client()
        ensure_collection(client)
        p = _make_payload()
        dense = [0.5] * 8
        sparse = _FakeSparse([0], [1.0])
        upsert_chunks([p], [dense], [sparse], client=client)
        delete_by_source_hash("nonexistent_hash", client=client)
        info = client.get_collection(_TEST_COLLECTION)
        assert info.points_count == 1


class TestBuildFilter:
    """Tests fuer _build_filter Hilfsfunktion."""

    def test_single_value_filter(self) -> None:
        """Einzelwert erzeugt MatchValue."""
        f = _build_filter({"doc_type": "handbuch"})
        assert len(f.must) == 1

    def test_list_value_filter(self) -> None:
        """Liste erzeugt MatchAny."""
        f = _build_filter({"bereich": ["forschung", "transfer"]})
        assert len(f.must) == 1

    def test_combined_filter(self) -> None:
        """Mehrere Keys erzeugen mehrere Conditions."""
        f = _build_filter({"doc_type": "handbuch", "herkunft": "lehrstuhl_at"})
        assert len(f.must) == 2
