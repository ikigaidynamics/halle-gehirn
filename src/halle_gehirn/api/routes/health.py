"""/health (liveness) + /ready (Qdrant+Ollama) -- Phase 6.

/health: Sofortige Antwort ohne externe Aufrufe (Kubernetes liveness).
/ready: Prueft Qdrant-Collection und Ollama-Modell-Verfuegbarkeit.
"""
from __future__ import annotations

import httpx
import structlog
from fastapi import APIRouter

from halle_gehirn.api.schemas import HealthResponse, ReadyResponse
from halle_gehirn.config import get_settings

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness-Check (kein externer Aufruf)."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse:
    """Readiness-Check: prueft Qdrant + Ollama Konnektivitaet."""
    settings = get_settings()
    qdrant_ok = _check_qdrant()
    ollama_ok = await _check_ollama(settings.ollama_url)
    status = "ready" if (qdrant_ok and ollama_ok) else "not_ready"
    return ReadyResponse(status=status, qdrant=qdrant_ok, ollama=ollama_ok)


def _check_qdrant() -> bool:
    """Prueft ob Qdrant erreichbar ist und Collection existiert."""
    try:
        from halle_gehirn.vector_store.qdrant_client import get_qdrant_client

        settings = get_settings()
        client = get_qdrant_client()
        return client.collection_exists(settings.qdrant_collection)
    except Exception as exc:
        logger.warning("readiness_qdrant_failed", error=str(exc))
        return False


async def _check_ollama(ollama_url: str) -> bool:
    """Prueft ob Ollama erreichbar ist."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{ollama_url}/api/tags")
            return resp.status_code == 200
    except Exception as exc:
        logger.warning("readiness_ollama_failed", error=str(exc))
        return False
