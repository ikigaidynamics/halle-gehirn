"""Qdrant-Client-Factory, Hybrid Query API, Snapshot/Erasure.

Einzige Instanziierungsstelle fuer den QdrantClient. Alle Operationen
arbeiten AUSSCHLIESSLICH auf der konfigurierten Collection (QDRANT_COLLECTION).
Andere Collections in derselben Instanz werden NIEMALS angefasst.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
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
    PointStruct,
    Prefetch,
    SparseVector,
)

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.pipeline.ingest import deterministic_chunk_id
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


# ────────────────────────── Erasure ──────────────────────────


def delete_by_source_hash(
    source_hash: str,
    client: QdrantClient | None = None,
) -> None:
    """Loescht alle Punkte mit gegebenem source_hash (Right-to-Erasure).

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
    logger.info(
        "erasure_done",
        source_hash=source_hash[:12],
        collection=s.qdrant_collection,
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
