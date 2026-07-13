"""FastAPI-App: Lifespan, CORS, Rate-Limit, OTEL -- Phase 6.

Zentraler Einstiegspunkt der API. Konfiguriert:
- Lifespan: Pipeline-Build + Check beim Start
- CORS fuer Streamlit-UI und Entwicklung
- In-Memory Rate-Limiting (Sliding Window per IP)
- OpenTelemetry-Instrumentation (optional)

Start: ``uvicorn halle_gehirn.api.main:app --host 0.0.0.0 --port 8001``
"""
from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from halle_gehirn.api.routes import admin, chat, health
from halle_gehirn.config import get_settings
from halle_gehirn.observability.logging_config import configure_logging
from halle_gehirn.pipeline.factory import build_query_pipeline
from halle_gehirn.pipeline.orchestrator import QueryOrchestrator

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifespan: baut Pipeline, loggt Infrastruktur-Status."""
    configure_logging(dev=True)
    settings = get_settings()

    logger.info(
        "startup_begin",
        ollama=settings.ollama_url,
        qdrant=settings.qdrant_url,
    )

    pipeline = build_query_pipeline(settings=settings)
    app.state.orchestrator = QueryOrchestrator(pipeline)
    app.state.settings = settings

    logger.info("startup_complete")
    yield
    logger.info("shutdown")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-Memory Sliding-Window Rate-Limiter per IP.

    Zaehlt Anfragen pro IP in einem 60-Sekunden-Fenster.
    Bei Ueberschreitung: 429 Too Many Requests.
    """

    def __init__(self, app: Any, rpm: int = 60) -> None:
        super().__init__(app)
        self._rpm = rpm
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(
        self, request: Request, call_next: Any,
    ) -> Response:
        """Prueft Rate-Limit vor Request-Verarbeitung."""
        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()

        # Alte Eintraege bereinigen
        timestamps = self._requests[client_ip]
        self._requests[client_ip] = [
            ts for ts in timestamps if ts > now - 60.0
        ]

        if len(self._requests[client_ip]) >= self._rpm:
            return Response(
                content="Rate limit exceeded",
                status_code=429,
                media_type="text/plain",
            )

        self._requests[client_ip].append(now)
        return await call_next(request)


def create_app() -> FastAPI:
    """Erzeugt und konfiguriert die FastAPI-App.

    Returns:
        Konfigurierte FastAPI-Instanz.
    """
    settings = get_settings()

    app = FastAPI(
        title="Halle-Gehirn API",
        description=(
            "RAG-API fuer den Lehrstuhl "
            "KI-gestuetzte Automatisierungstechnik"
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — konfigurierte Origins + automatisch localhost:8501-8510
    # damit Streamlit auch auf Alternativ-Ports funktioniert.
    origins = {
        o.strip() for o in settings.cors_origins.split(",") if o.strip()
    }
    for port in range(8501, 8511):
        origins.add(f"http://localhost:{port}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate-Limit
    app.add_middleware(RateLimitMiddleware, rpm=settings.rate_limit_rpm)

    # OTEL (optional)
    if settings.otel_enabled:
        try:
            from opentelemetry.instrumentation.fastapi import (
                FastAPIInstrumentor,
            )

            FastAPIInstrumentor.instrument_app(app)
            logger.info("otel_instrumented")
        except ImportError:
            logger.warning("otel_not_available")

    # Router
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(admin.router)

    return app


app = create_app()
