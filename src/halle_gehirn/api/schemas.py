"""Pydantic Request/Response-Schemas -- Phase 6.

Definiert die API-Contracts fuer /chat, /chat/stream, /health und /admin.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request fuer /chat und /chat/stream."""

    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(default="", max_length=64)
    filters: dict[str, str | list[str]] | None = None
    debug: bool = False


class Source(BaseModel):
    """Eine Quellen-Referenz in der Antwort.

    Feldmenge MUSS mit ``orchestrator._build_sources`` uebereinstimmen —
    sonst liefern /chat (Pydantic) und /chat/stream (raw dict)
    unterschiedliche Vertraege (Vertrags-Test in test_api.py).
    """

    id: str
    titel: str
    url: str | None = None
    datei: str = ""
    snippet: str = ""
    page: int | None = None
    score: float = 0.0
    doc_type: str = ""
    breadcrumb: str = ""


class ChatResponse(BaseModel):
    """Response fuer /chat (nicht-streaming)."""

    answer: str
    confidence: str
    sources: list[Source] = Field(default_factory=list)
    latency_ms: float = 0.0
    debug_info: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    """Response fuer /health."""

    status: str = "ok"


class ReadyResponse(BaseModel):
    """Response fuer /ready."""

    status: str
    qdrant: bool = False
    ollama: bool = False


class AdminResponse(BaseModel):
    """Response fuer Admin-Endpunkte."""

    status: str
    message: str = ""
