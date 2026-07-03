"""/admin (X-API-Key): reindex, eval, erasure -- Phase 6.

Alle Admin-Endpunkte erfordern einen gueltigen X-API-Key Header.
Ohne Key -> 401 Unauthorized.
"""
from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException

from halle_gehirn.api.schemas import AdminResponse
from halle_gehirn.config import get_settings
from halle_gehirn.vector_store.qdrant_client import delete_by_source_hash

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


async def verify_api_key(
    x_api_key: Annotated[str | None, Header()] = None,
) -> str:
    """Prueft den X-API-Key Header.

    Args:
        x_api_key: Der API-Key aus dem Header.

    Returns:
        Der verifizierte API-Key.

    Raises:
        HTTPException: 401 wenn Key fehlt oder ungueltig.
    """
    settings = get_settings()
    if not x_api_key or x_api_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Ungueltiger API-Key")
    return x_api_key


@router.post("/reindex", response_model=AdminResponse)
async def reindex(
    _key: Annotated[str, Depends(verify_api_key)],
) -> AdminResponse:
    """Triggert einen Reindex-Lauf.

    Returns:
        Status-Meldung (Platzhalter fuer Phase 8).
    """
    logger.info("admin_reindex_triggered")
    return AdminResponse(
        status="accepted",
        message="Reindex wurde gestartet. Fortschritt im Log.",
    )


@router.post("/eval", response_model=AdminResponse)
async def eval_run(
    _key: Annotated[str, Depends(verify_api_key)],
) -> AdminResponse:
    """Triggert einen Eval-Lauf.

    Returns:
        Status-Meldung (Platzhalter fuer Phase 8).
    """
    logger.info("admin_eval_triggered")
    return AdminResponse(
        status="accepted",
        message="Eval-Lauf wurde gestartet.",
    )


@router.delete("/erasure/{source_hash}", response_model=AdminResponse)
async def erasure(
    source_hash: str,
    _key: Annotated[str, Depends(verify_api_key)],
) -> AdminResponse:
    """Loescht alle Chunks mit gegebenem source_hash (Right-to-Erasure).

    Args:
        source_hash: SHA256-Hash der zu loeschenden Quelle.

    Returns:
        Bestaetigungsmeldung.

    Raises:
        HTTPException: 500 bei Qdrant-Fehler.
    """
    try:
        delete_by_source_hash(source_hash)
        logger.info("admin_erasure_done", source_hash=source_hash[:12])
        return AdminResponse(
            status="ok",
            message=f"Chunks mit source_hash={source_hash[:12]}... geloescht.",
        )
    except Exception as exc:
        logger.error("admin_erasure_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
