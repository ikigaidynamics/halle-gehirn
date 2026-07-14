"""Qdrant-Client-Factory, Hybrid Query API, Snapshot/Erasure.

Einzige Instanziierungsstelle fuer den QdrantClient. Alle Operationen
arbeiten AUSSCHLIESSLICH auf der konfigurierten Collection (QDRANT_COLLECTION).
Andere Collections in derselben Instanz werden NIEMALS angefasst.
"""
from __future__ import annotations

import hashlib
import shutil
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    Fusion,
    FusionQuery,
    MatchAny,
    MatchValue,
    PointIdsList,
    PointStruct,
    Prefetch,
    Range,
    SparseVector,
)

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.vector_store.schema import (
    ChunkPayload,
    create_collection_if_missing,
)

logger = structlog.get_logger(__name__)

_UPSERT_BATCH = 100


class QdrantError(Exception):
    """Fehler bei Qdrant-Operationen."""


# ────────────────────────── Factory ──────────────────────────


@lru_cache
def get_qdrant_client(settings: Settings | None = None) -> QdrantClient:
    """Einzige Instanziierungsstelle fuer den QdrantClient.

    Args:
        settings: Optionale Settings (Default: get_settings()).

    Returns:
        Gecachter QdrantClient.
    """
    s = settings or get_settings()
    client = QdrantClient(url=s.qdrant_url, timeout=60)
    logger.info("qdrant_client_created", url=s.qdrant_url)
    return client


# ────────────────────────── Collection ──────────────────────────


def ensure_collection(client: QdrantClient | None = None) -> None:
    """Stellt sicher, dass die Collection existiert (idempotent).

    Delegiert an schema.create_collection_if_missing().

    Args:
        client: Optionaler QdrantClient (Default: get_qdrant_client()).
    """
    c = client or get_qdrant_client()
    create_collection_if_missing(c)
    s = get_settings()
    logger.info("collection_ensured", collection=s.qdrant_collection)


def reset_collection(client: QdrantClient | None = None) -> None:
    """Loescht und erstellt die konfigurierte Collection neu.

    AUSSCHLIESSLICH die Collection aus QDRANT_COLLECTION wird geloescht.
    Keine andere Collection wird angefasst.

    Args:
        client: Optionaler QdrantClient.
    """
    c = client or get_qdrant_client()
    s = get_settings()
    collection = s.qdrant_collection
    if c.collection_exists(collection):
        c.delete_collection(collection)
        logger.warning("collection_deleted", collection=collection)
    create_collection_if_missing(c)
    logger.info("collection_recreated", collection=collection)


# ────────────────────────── Upsert ──────────────────────────


def upsert_chunks(
    payloads: list[ChunkPayload],
    dense_vecs: list[list[float]],
    sparse_vecs: list[Any],
    client: QdrantClient | None = None,
) -> int:
    """Upserted Chunks mit Named Vectors (dense+sparse) + Payload.

    Verwendet deterministische IDs (source_hash + chunk_index) fuer
    idempotenten Re-Ingest.

    Args:
        payloads: Liste von ChunkPayloads.
        dense_vecs: Dense-Vektoren (je 1024d).
        sparse_vecs: Sparse-Vektoren (fastembed-Objekte mit .indices/.values).
        client: Optionaler QdrantClient.

    Returns:
        Anzahl der upgeserteten Punkte.

    Raises:
        QdrantError: Laengen stimmen nicht ueberein.
    """
    if len(payloads) != len(dense_vecs) or len(payloads) != len(sparse_vecs):
        raise QdrantError(
            f"Laengen-Mismatch: payloads={len(payloads)}, "
            f"dense={len(dense_vecs)}, sparse={len(sparse_vecs)}"
        )
    if not payloads:
        return 0

    c = client or get_qdrant_client()
    s = get_settings()
    ensure_collection(c)

    points = _build_points(payloads, dense_vecs, sparse_vecs)
    total = 0
    for batch_start in range(0, len(points), _UPSERT_BATCH):
        batch = points[batch_start : batch_start + _UPSERT_BATCH]
        c.upsert(collection_name=s.qdrant_collection, points=batch)
        total += len(batch)
        logger.debug("upsert_batch", count=len(batch), total=total)

    logger.info("upsert_done", total=total, collection=s.qdrant_collection)
    return total


def deterministic_chunk_id(source_hash: str, chunk_index: int) -> str:
    """Erzeugt eine deterministische Chunk-ID.

    Args:
        source_hash: SHA256-Hash der Quelldatei.
        chunk_index: Index des Chunks im Dokument.

    Returns:
        Hex-String der deterministischen ID.
    """
    return hashlib.sha256(
        f"{source_hash}:{chunk_index}".encode()
    ).hexdigest()[:32]


def _build_points(
    payloads: list[ChunkPayload],
    dense_vecs: list[list[float]],
    sparse_vecs: list[Any],
) -> list[PointStruct]:
    """Baut PointStruct-Objekte mit Named Vectors + Payload."""
    points: list[PointStruct] = []
    for payload, dense, sparse in zip(
        payloads, dense_vecs, sparse_vecs, strict=True,
    ):
        point_id = deterministic_chunk_id(
            payload.source_hash, payload.chunk_index,
        )
        sparse_indices = (
            sparse.indices.tolist()
            if hasattr(sparse.indices, "tolist")
            else list(sparse.indices)
        )
        sparse_values = (
            sparse.values.tolist()
            if hasattr(sparse.values, "tolist")
            else list(sparse.values)
        )
        points.append(PointStruct(
            id=point_id,
            vector={
                "dense": dense,
                "sparse": SparseVector(
                    indices=sparse_indices,
                    values=sparse_values,
                ),
            },
            payload=payload.model_dump(mode="json"),
        ))
    return points


# ────────────────────────── Hybrid Query ──────────────────────────


@dataclass
class RetrievalHit:
    """Ein Treffer aus der Hybrid-Query."""

    point_id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)
    rerank_score: float = 0.0


def hybrid_query(
    query_dense: list[float],
    query_sparse: Any,
    limit: int | None = None,
    filters: dict[str, Any] | None = None,
    client: QdrantClient | None = None,
) -> list[RetrievalHit]:
    """Hybrid Query via Qdrant Query API (prefetch dense+sparse, Fusion).

    Args:
        query_dense: Dense-Query-Vektor (1024d).
        query_sparse: Sparse-Query-Vektor (fastembed-Objekt).
        limit: Anzahl Treffer (Default: top_k_initial aus Config).
        filters: Optionale Payload-Filter (key -> value/list).
        client: Optionaler QdrantClient.

    Returns:
        Liste von RetrievalHit (absteigend nach Score).
    """
    c = client or get_qdrant_client()
    s = get_settings()
    result_limit = limit or s.top_k_initial

    sparse_indices = (
        query_sparse.indices.tolist()
        if hasattr(query_sparse.indices, "tolist")
        else list(query_sparse.indices)
    )
    sparse_values = (
        query_sparse.values.tolist()
        if hasattr(query_sparse.values, "tolist")
        else list(query_sparse.values)
    )
    sparse_vec = SparseVector(indices=sparse_indices, values=sparse_values)

    qdrant_filter = _build_filter(filters) if filters else None
    fusion = Fusion.RRF if s.fusion == "rrf" else Fusion.DBSF

    response = c.query_points(
        collection_name=s.qdrant_collection,
        prefetch=[
            Prefetch(
                query=query_dense,
                using="dense",
                limit=result_limit,
                filter=qdrant_filter,
            ),
            Prefetch(
                query=sparse_vec,
                using="sparse",
                limit=result_limit,
                filter=qdrant_filter,
            ),
        ],
        query=FusionQuery(fusion=fusion),
        limit=result_limit,
        with_payload=True,
    )
    hits = [
        RetrievalHit(
            point_id=str(pt.id),
            score=pt.score or 0.0,
            payload=pt.payload or {},
        )
        for pt in response.points
    ]
    logger.info(
        "hybrid_query_done",
        hits=len(hits),
        fusion=s.fusion,
        limit=result_limit,
    )
    return hits


def _build_filter(filters: dict[str, Any]) -> Filter:
    """Baut Qdrant-Filter aus einem einfachen Key-Value-Dict.

    Unterstuetzt Einzelwerte (MatchValue) und Listen (MatchAny).

    Args:
        filters: Dict mit Feld-Name -> Wert oder Liste von Werten.

    Returns:
        Qdrant Filter-Objekt.
    """
    conditions: list[FieldCondition] = []
    for key, value in filters.items():
        if isinstance(value, list):
            conditions.append(
                FieldCondition(key=key, match=MatchAny(any=value))
            )
        else:
            conditions.append(
                FieldCondition(key=key, match=MatchValue(value=value))
            )
    return Filter(must=conditions)  # type: ignore[arg-type]


# ────────────────────────── Inspektion ──────────────────────────


def list_indexed_documents(
    client: QdrantClient | None = None,
) -> list[dict[str, Any]]:
    """Listet alle indexierten Dokumente (gruppiert nach datei).

    Scrollt die gesamte Collection und gruppiert Chunks nach dem
    ``datei``-Payload-Feld.

    Args:
        client: Optionaler QdrantClient.

    Returns:
        Liste von Dicts mit datei, titel, chunk_count, source_hash.
    """
    c = client or get_qdrant_client()
    s = get_settings()

    if not c.collection_exists(s.qdrant_collection):
        return []

    docs: dict[str, dict[str, Any]] = {}
    offset = None

    while True:
        results, next_offset = c.scroll(
            collection_name=s.qdrant_collection,
            limit=100,
            offset=offset,
            with_payload=["datei", "titel", "source_hash", "doc_type"],
            with_vectors=False,
        )
        for point in results:
            payload = point.payload or {}
            datei = payload.get("datei", "")
            if datei not in docs:
                docs[datei] = {
                    "datei": datei,
                    "titel": payload.get("titel", "Unbekannt"),
                    "source_hash": payload.get("source_hash", ""),
                    "doc_type": payload.get("doc_type", ""),
                    "chunk_count": 0,
                }
            docs[datei]["chunk_count"] += 1

        if next_offset is None:
            break
        offset = next_offset

    return sorted(docs.values(), key=lambda d: d["datei"])


def get_chunks_by_datei(
    datei: str,
    client: QdrantClient | None = None,
) -> list[dict[str, Any]]:
    """Gibt alle Chunks eines Dokuments zurueck (nach datei gefiltert).

    Args:
        datei: Der Dateipfad (z.B. 'anlagen/test_anlage_roboter.pdf').
        client: Optionaler QdrantClient.

    Returns:
        Liste von Dicts mit point_id und vollstaendigem Payload,
        sortiert nach chunk_index.
    """
    c = client or get_qdrant_client()
    s = get_settings()

    if not c.collection_exists(s.qdrant_collection):
        return []

    chunks: list[dict[str, Any]] = []
    offset = None

    while True:
        results, next_offset = c.scroll(
            collection_name=s.qdrant_collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="datei",
                        match=MatchValue(value=datei),
                    )
                ]
            ),
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in results:
            chunks.append({
                "point_id": str(point.id),
                "payload": point.payload or {},
            })

        if next_offset is None:
            break
        offset = next_offset

    chunks.sort(key=lambda c: c["payload"].get("chunk_index", 0))
    return chunks


# ────────────────────────── Delta-Hygiene ──────────────────────────


def delete_stale_chunks(
    datei: str,
    current_hash: str,
    expected_chunk_count: int,
    client: QdrantClient | None = None,
) -> int:
    """Loescht veraltete Punkte eines Dokuments nach dem Re-Ingest.

    Zwei Kategorien werden entfernt:
    1. Punkte derselben ``datei`` mit ANDEREM ``source_hash``
       (alte Dokumentversion — neue IDs, alte blieben sonst stehen).
    2. Punkte mit gleichem ``source_hash``, aber ``chunk_index`` >=
       *expected_chunk_count* (das Chunking lieferte diesmal weniger
       Chunks, z.B. nach Filter-Aenderungen).

    Args:
        datei: Manifest-Pfad des Dokuments (Payload-Feld ``datei``).
        current_hash: Aktueller SHA256 der Quelldatei.
        expected_chunk_count: Anzahl Chunks des aktuellen Laufs.
        client: Optionaler QdrantClient.

    Returns:
        Anzahl geloeschter Punkte.
    """
    c = client or get_qdrant_client()
    s = get_settings()
    if not c.collection_exists(s.qdrant_collection):
        return 0

    stale_filter = Filter(
        should=[
            Filter(
                must=[FieldCondition(
                    key="datei", match=MatchValue(value=datei),
                )],
                must_not=[FieldCondition(
                    key="source_hash", match=MatchValue(value=current_hash),
                )],
            ),
            Filter(
                must=[
                    FieldCondition(
                        key="source_hash",
                        match=MatchValue(value=current_hash),
                    ),
                    FieldCondition(
                        key="chunk_index",
                        range=Range(gte=expected_chunk_count),
                    ),
                ],
            ),
        ],
    )
    count = c.count(
        collection_name=s.qdrant_collection,
        count_filter=stale_filter,
        exact=True,
    ).count
    if count == 0:
        return 0
    c.delete(
        collection_name=s.qdrant_collection,
        points_selector=FilterSelector(filter=stale_filter),
    )
    logger.info(
        "stale_chunks_deleted",
        datei=datei,
        count=count,
        current_hash=current_hash[:12],
        collection=s.qdrant_collection,
    )
    return count


# ────────────────────────── Erasure ──────────────────────────


def delete_by_source_hash(
    source_hash: str,
    client: QdrantClient | None = None,
) -> None:
    """Loescht alle Punkte mit gegebenem source_hash (Right-to-Erasure).

    Entfernt auch das zugehoerige Abbildungs-Verzeichnis
    ``{figures_dir}/{source_hash[:16]}/`` falls vorhanden.

    Args:
        source_hash: SHA256-Hash der Quelldatei.
        client: Optionaler QdrantClient.
    """
    c = client or get_qdrant_client()
    s = get_settings()
    c.delete(
        collection_name=s.qdrant_collection,
        points_selector=FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(
                        key="source_hash",
                        match=MatchValue(value=source_hash),
                    )
                ]
            )
        ),
    )
    # Abbildungen auf Disk entfernen (graceful bei fehlendem Verzeichnis)
    fig_dir = Path(s.figures_dir) / source_hash[:16]
    if fig_dir.is_dir():
        shutil.rmtree(fig_dir)
        logger.info("figures_dir_deleted", path=str(fig_dir))
    logger.info(
        "erasure_done",
        source_hash=source_hash[:12],
        collection=s.qdrant_collection,
    )


def delete_points_by_ids(
    point_ids: Sequence[str],
    client: QdrantClient | None = None,
) -> None:
    """Loescht einzelne Punkte anhand ihrer IDs.

    Args:
        point_ids: Sequenz von Punkt-IDs (hex-Strings).
        client: Optionaler QdrantClient.
    """
    if not point_ids:
        return
    c = client or get_qdrant_client()
    s = get_settings()
    c.delete(
        collection_name=s.qdrant_collection,
        points_selector=PointIdsList(points=list(point_ids)),
    )
    logger.info(
        "points_deleted",
        count=len(point_ids),
        ids=[pid[:12] for pid in point_ids[:5]],
        collection=s.qdrant_collection,
    )


def update_point_payload(
    point_id: str,
    payload_updates: dict[str, Any],
    client: QdrantClient | None = None,
) -> None:
    """Aktualisiert Payload-Felder eines einzelnen Punktes.

    Args:
        point_id: Punkt-ID (hex-String).
        payload_updates: Dict mit zu aktualisierenden Feldern.
        client: Optionaler QdrantClient.
    """
    c = client or get_qdrant_client()
    s = get_settings()
    c.set_payload(
        collection_name=s.qdrant_collection,
        payload=payload_updates,
        points=[point_id],
    )
    logger.info(
        "payload_updated",
        point_id=point_id[:12],
        fields=list(payload_updates.keys()),
    )


# ────────────────────────── Snapshot ──────────────────────────


def create_snapshot(
    client: QdrantClient | None = None,
) -> str:
    """Erstellt einen Snapshot der konfigurierten Collection.

    Args:
        client: Optionaler QdrantClient.

    Returns:
        Name der Snapshot-Datei.
    """
    c = client or get_qdrant_client()
    s = get_settings()
    info = c.create_snapshot(collection_name=s.qdrant_collection)
    assert info is not None, "Snapshot-Erstellung fehlgeschlagen"
    name = info.name
    logger.info("snapshot_created", name=name, collection=s.qdrant_collection)
    return name


def list_snapshots(
    client: QdrantClient | None = None,
) -> list[dict[str, Any]]:
    """Listet alle Snapshots der konfigurierten Collection.

    Args:
        client: Optionaler QdrantClient.

    Returns:
        Liste von Snapshot-Infos (name, size, creation_time).
    """
    c = client or get_qdrant_client()
    s = get_settings()
    snaps = c.list_snapshots(collection_name=s.qdrant_collection)
    return [
        {
            "name": snap.name,
            "size": snap.size,
            "creation_time": str(snap.creation_time),
        }
        for snap in snaps
    ]
