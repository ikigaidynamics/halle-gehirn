"""Tests fuer Phase 6 -- API-Schicht.

Testet /health, /ready, /admin (Auth), /chat, /chat/stream.
Alle externen Dienste (Qdrant, Ollama, LLM) werden gemockt.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from halle_gehirn.api.main import create_app
from halle_gehirn.config import Settings, get_settings
from halle_gehirn.generator.openai_client import GeneratorError
from halle_gehirn.pipeline.orchestrator import QueryResult


def _test_settings(**overrides: Any) -> Settings:
    """Settings fuer Tests (keine externen Dienste)."""
    defaults: dict[str, Any] = {
        "qdrant_url": "http://localhost:6335",
        "qdrant_collection": "halle_wissen_test",
        "ollama_url": "http://localhost:11434",
        "admin_api_key": "test-secret-key",
        "cors_origins": "*",
        "rate_limit_rpm": 1000,
        "use_query_transform": False,
        "use_grounding_check": False,
        "otel_enabled": False,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _mock_orchestrator(result: QueryResult | None = None) -> MagicMock:
    """Erzeugt einen gemockten QueryOrchestrator."""
    orch = MagicMock()
    orch.run = AsyncMock(return_value=result or QueryResult(
        answer="Testantwort [S1].",
        confidence="gruen",
        sources=[{
            "id": "S1",
            "titel": "Testdoc",
            "url": "https://example.com",
            "snippet": "Testinhalt",
            "page": 1,
            "score": 0.85,
        }],
        latency_ms=42.0,
    ))
    return orch


@contextmanager
def _patched_app(
    orchestrator: MagicMock | None = None,
) -> Any:
    """Erzeugt App mit gepatchter Pipeline + Settings.

    Patches bleiben waehrend des gesamten Test-Lifecycle aktiv
    (inkl. Lifespan und Request-Handling). get_settings wird an
    allen Import-Stellen gepatcht.
    """
    get_settings.cache_clear()
    settings = _test_settings()
    with (
        patch("halle_gehirn.config.get_settings", return_value=settings),
        patch(
            "halle_gehirn.api.main.get_settings",
            return_value=settings,
        ),
        patch(
            "halle_gehirn.api.routes.admin.get_settings",
            return_value=settings,
        ),
        patch(
            "halle_gehirn.api.routes.health.get_settings",
            return_value=settings,
        ),
        patch("halle_gehirn.api.main.build_query_pipeline") as mock_build,
    ):
        mock_pipeline = MagicMock()
        mock_pipeline.settings = settings
        mock_build.return_value = mock_pipeline

        app = create_app()
        if orchestrator:
            app.state.orchestrator = orchestrator
        with TestClient(app) as client:
            if orchestrator:
                app.state.orchestrator = orchestrator
            yield client


class TestHealthEndpoints:
    """Tests fuer /health und /ready."""

    def test_health_returns_ok(self) -> None:
        """GET /health gibt immer 200 zurueck."""
        with _patched_app() as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    @patch(
        "halle_gehirn.api.routes.health._check_qdrant",
        return_value=True,
    )
    @patch(
        "halle_gehirn.api.routes.health._check_llm",
        new_callable=AsyncMock,
        return_value=True,
    )
    def test_ready_all_ok(
        self, _mock_llm: AsyncMock, _mock_qdrant: MagicMock,
    ) -> None:
        """GET /ready mit allen Diensten verfuegbar."""
        with _patched_app() as client:
            resp = client.get("/ready")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ready"
            assert data["qdrant"] is True
            assert data["ollama"] is True

    @patch(
        "halle_gehirn.api.routes.health._check_qdrant",
        return_value=False,
    )
    @patch(
        "halle_gehirn.api.routes.health._check_llm",
        new_callable=AsyncMock,
        return_value=True,
    )
    def test_ready_qdrant_down(
        self, _mock_llm: AsyncMock, _mock_qdrant: MagicMock,
    ) -> None:
        """GET /ready mit Qdrant nicht erreichbar -> 503."""
        with _patched_app() as client:
            resp = client.get("/ready")
            assert resp.status_code == 503
            data = resp.json()
            assert data["status"] == "not_ready"
            assert data["qdrant"] is False


class TestAdminAuth:
    """Tests fuer Admin-Endpunkt-Authentifizierung."""

    def test_admin_without_key_returns_401(self) -> None:
        """POST /admin/reindex ohne Key -> 401."""
        with _patched_app() as client:
            resp = client.post("/admin/reindex")
            assert resp.status_code == 401

    def test_admin_with_wrong_key_returns_401(self) -> None:
        """POST /admin/reindex mit falschem Key -> 401."""
        with _patched_app() as client:
            resp = client.post(
                "/admin/reindex",
                headers={"X-API-Key": "wrong-key"},
            )
            assert resp.status_code == 401

    def test_admin_with_valid_key_returns_200(self) -> None:
        """POST /admin/reindex mit gueltigem Key -> 200."""
        with _patched_app() as client:
            resp = client.post(
                "/admin/reindex",
                headers={"X-API-Key": "test-secret-key"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "accepted"

    @patch("halle_gehirn.api.routes.admin.delete_by_source_hash")
    def test_erasure_with_valid_key(
        self, mock_delete: MagicMock,
    ) -> None:
        """DELETE /admin/erasure/{hash} mit Key -> 200."""
        with _patched_app() as client:
            resp = client.delete(
                "/admin/erasure/abc123def456",
                headers={"X-API-Key": "test-secret-key"},
            )
            assert resp.status_code == 200
            mock_delete.assert_called_once_with("abc123def456")


class TestChatEndpoints:
    """Tests fuer /chat und /chat/stream."""

    def test_chat_returns_answer(self) -> None:
        """POST /chat gibt Antwort mit Quellen zurueck."""
        with _patched_app(orchestrator=_mock_orchestrator()) as client:
            resp = client.post("/chat", json={"query": "Testfrage"})
            assert resp.status_code == 200
            data = resp.json()
            assert "Testantwort" in data["answer"]
            assert data["confidence"] == "gruen"
            assert len(data["sources"]) == 1

    def test_chat_stream_returns_sse(self) -> None:
        """POST /chat/stream gibt SSE-Events zurueck."""
        orch = MagicMock()

        async def mock_stream(**kwargs: Any) -> Any:
            yield {"type": "token", "content": "Test"}
            yield {"type": "token", "content": "antwort"}
            yield {
                "type": "done",
                "confidence": "gruen",
                "sources": [],
                "latency_ms": 10.0,
            }

        orch.run_stream = mock_stream

        with _patched_app(orchestrator=orch) as client:
            resp = client.post(
                "/chat/stream",
                json={"query": "Testfrage"},
            )
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]

            raw_lines = [
                raw for raw in resp.text.strip().split("\n\n")
                if raw.startswith("data: ")
            ]
            events = [
                json.loads(raw.removeprefix("data: "))
                for raw in raw_lines
            ]
            token_events = [e for e in events if e["type"] == "token"]
            done_events = [e for e in events if e["type"] == "done"]
            assert len(token_events) == 2
            assert len(done_events) == 1
            assert done_events[0]["confidence"] == "gruen"

    def test_chat_stream_error_event_on_generator_failure(self) -> None:
        """Pipeline-Fehler im Stream -> error-Event statt ASGI-Abbruch."""
        orch = MagicMock()

        async def failing_stream(**kwargs: Any) -> Any:
            yield {"type": "token", "content": "Anfang"}
            raise GeneratorError("Connection error: All connection attempts failed")

        orch.run_stream = failing_stream

        with _patched_app(orchestrator=orch) as client:
            resp = client.post(
                "/chat/stream",
                json={"query": "Testfrage"},
            )
            assert resp.status_code == 200
            raw_lines = [
                raw for raw in resp.text.strip().split("\n\n")
                if raw.startswith("data: ")
            ]
            events = [
                json.loads(raw.removeprefix("data: "))
                for raw in raw_lines
            ]
            error_events = [e for e in events if e["type"] == "error"]
            assert len(error_events) == 1
            assert "Fehler" in error_events[0]["message"]

    def test_chat_empty_query_returns_422(self) -> None:
        """POST /chat mit leerer Query -> 422 Validation Error."""
        with _patched_app(orchestrator=_mock_orchestrator()) as client:
            resp = client.post("/chat", json={"query": ""})
            assert resp.status_code == 422
