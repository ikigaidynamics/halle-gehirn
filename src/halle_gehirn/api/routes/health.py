"""/health (liveness) + /ready (Qdrant + LLM-Backend) -- Phase 6.

/health: Sofortige Antwort ohne externe Aufrufe (Kubernetes liveness).
/ready: Prueft Qdrant-Collection und Erreichbarkeit des konfigurierten
LLM-Backends (Ollama ``/api/tags`` oder OpenAI-kompatibel ``/models``).
"""
from __future__ import annotations

from typing import Any

import httpx
import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from halle_gehirn.api.schemas import HealthResponse, ReadyResponse
from halle_gehirn.config import get_settings

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness-Check (kein externer Aufruf)."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadyResponse)
async def ready() -> JSONResponse:
    """Readiness-Check: prueft Qdrant + konfiguriertes LLM-Backend.

    HTTP-Status: 200 wenn ready, sonst 503 (Konvention fuer
    Readiness-Probes, damit Monitoring defekte Backends erkennt).
    """
    settings = get_settings()
    qdrant_ok = _check_qdrant()
    llm_ok = await _check_llm(settings)
    ready_all = qdrant_ok and llm_ok
    body = ReadyResponse(
        status="ready" if ready_all else "not_ready",
        qdrant=qdrant_ok, ollama=llm_ok,
        llm_backend=settings.llm_backend,
    )
    return JSONResponse(
        status_code=200 if ready_all else 503,
        content=body.model_dump(),
    )


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


async def _check_llm(settings: Any) -> bool:
    """Prueft die Erreichbarkeit des konfigurierten LLM-Backends."""
    if settings.llm_backend == "openai":
        return await _check_openai(settings.openai_base_url)
    return await _check_ollama(settings.ollama_url)


async def _check_ollama(ollama_url: str) -> bool:
    """Prueft ob Ollama erreichbar ist."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{ollama_url}/api/tags")
            return resp.status_code == 200
    except Exception as exc:
        logger.warning("readiness_ollama_failed", error=str(exc))
        return False


async def _check_openai(base_url: str) -> bool:
    """Prueft ob ein OpenAI-kompatibles Backend erreichbar ist."""
    if not base_url:
        logger.warning("readiness_openai_missing_base_url")
        return False
    try:
        url = base_url.rstrip("/")
        url = url[: -len("/v1")] if url.endswith("/v1") else url
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{url}/v1/models")
            return resp.status_code == 200
    except Exception as exc:
        logger.warning("readiness_openai_failed", error=str(exc))
        return False
