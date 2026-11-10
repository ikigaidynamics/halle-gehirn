"""/chat + /chat/stream (SSE Token-by-Token) -- Phase 6.

POST /chat: Vollstaendige Antwort (JSON).
POST /chat/stream: Server-Sent Events mit Token-by-Token Streaming.
Nur content-Tokens -- kein thinking-Feld (in Phase 5 geloest).
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import structlog
from fastapi import APIRouter, Request
from starlette.responses import StreamingResponse

from halle_gehirn.api.schemas import ChatRequest, ChatResponse, LatencyStats, Source

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    """Verarbeitet eine Chat-Anfrage (nicht-streaming).

    Args:
        body: Die ChatRequest mit Query und Optionen.
        request: FastAPI Request (fuer app.state Zugriff).

    Returns:
        ChatResponse mit Antwort, Konfidenz und Quellen.
    """
    orchestrator = request.app.state.orchestrator
    result = await orchestrator.run(
        query=body.query,
        session_id=body.session_id,
        filters=body.filters,
        debug=body.debug,
    )
    sources = [Source(**s) for s in result.sources]
    stats = None
    if result.stats:
        stats = LatencyStats(
            rewrite_ms=result.stats.rewrite_ms,
            embed_ms=result.stats.embed_ms,
            search_ms=result.stats.search_ms,
            rerank_ms=result.stats.rerank_ms,
            generate_ms=result.stats.generate_ms,
            total_ms=result.stats.total_ms,
        )
    return ChatResponse(
        answer=result.answer,
        confidence=result.confidence,
        sources=sources,
        latency_ms=round(result.latency_ms, 1),
        stats=stats,
        debug_info=result.debug_info if body.debug else None,
    )


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest, request: Request,
) -> StreamingResponse:
    """Streamt die Antwort als Server-Sent Events.

    SSE-Format:
    - data: {"type": "token", "content": "..."}
    - data: {"type": "done", "confidence": "...", "sources": [...]}

    Args:
        body: Die ChatRequest.
        request: FastAPI Request.

    Returns:
        StreamingResponse mit text/event-stream Content-Type.
    """
    orchestrator = request.app.state.orchestrator

    async def event_generator() -> AsyncIterator[str]:
        """Generiert SSE-Events aus dem Orchestrator-Stream."""
        async for event in orchestrator.run_stream(
            query=body.query,
            session_id=body.session_id,
            filters=body.filters,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
