"""Tests fuer die backend-abhaengige LLM-Client-Factory.

Prueft: Backend-Auswahl (llm_backend), Ollama-Shape der OpenAI-Antwort,
Fail-Fast bei fehlender OPENAI_BASE_URL, und Backend-Awareness des
/ready-Checks.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from halle_gehirn.config import Settings
from halle_gehirn.generator.llm_client import (
    OllamaLLMClient,
    OpenAILLMClient,
    get_llm_client,
)


def _settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "llm_model": "qwen3:8b",
        "ollama_url": "http://localhost:11434",
        "openai_base_url": "http://vllm.test:8080/v1",
        "openai_model": "",
    }
    defaults.update(overrides)
    return Settings(**defaults)


class TestFactorySelection:
    """get_llm_client waehlt gemäss llm_backend."""

    def test_default_is_ollama(self) -> None:
        client = get_llm_client(settings=_settings(llm_backend="ollama"))
        assert isinstance(client, OllamaLLMClient)

    def test_openai_backend_selects_openai_client(self) -> None:
        client = get_llm_client(settings=_settings(llm_backend="openai"))
        assert isinstance(client, OpenAILLMClient)

    def test_openai_client_model_prefers_openai_model(self) -> None:
        client = get_llm_client(
            settings=_settings(llm_backend="openai", openai_model="llama-3.1"),
        )
        assert client.model == "llama-3.1"

    def test_openai_client_model_falls_back_to_llm_model(self) -> None:
        client = get_llm_client(settings=_settings(llm_backend="openai"))
        assert client.model == "qwen3:8b"

    def test_missing_base_url_fails_fast(self) -> None:
        with pytest.raises(ValueError, match="OPENAI_BASE_URL"):
            get_llm_client(
                settings=_settings(llm_backend="openai", openai_base_url=""),
            )


class TestOpenAIClientChat:
    """OpenAILLMClient.chat uebersetzt in das Ollama-Antwortformat."""

    def test_chat_returns_ollama_shape(self) -> None:
        client = OpenAILLMClient(settings=_settings(llm_backend="openai"))
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": "Ja"}}],
        }
        with patch(
            "halle_gehirn.generator.llm_client.httpx.post",
            return_value=response,
        ) as mock_post:
            result = client.chat(
                model="qwen3:8b",
                messages=[{"role": "user", "content": "Test"}],
                options={"temperature": 0.0, "num_predict": 8},
            )

        assert result == {"message": {"content": "Ja"}}
        payload = mock_post.call_args.kwargs["json"]
        assert payload["max_tokens"] == 8
        assert payload["temperature"] == 0.0
        assert payload["stream"] is False

    def test_chat_error_raises(self) -> None:
        client = OpenAILLMClient(settings=_settings(llm_backend="openai"))
        response = MagicMock()
        response.status_code = 500
        response.text = "Internal Server Error"
        with (
            patch(
                "halle_gehirn.generator.llm_client.httpx.post",
                return_value=response,
            ),
            pytest.raises(RuntimeError, match="OpenAI LLM error 500"),
        ):
            client.chat(
                model="qwen3:8b",
                messages=[{"role": "user", "content": "Test"}],
            )


class TestStageClientsBackendAware:
    """Interne Stages nutzen bei openai das OpenAI-Backend."""

    def test_query_rewriter_uses_openai_client(self) -> None:
        from halle_gehirn.retrieval.query_rewriter import QueryRewriter

        rewriter = QueryRewriter(settings=_settings(llm_backend="openai"))
        assert isinstance(rewriter._client, OpenAILLMClient)

    def test_faithfulness_checker_uses_openai_client(self) -> None:
        from halle_gehirn.pipeline.stages.grounding import FaithfulnessChecker

        checker = FaithfulnessChecker(settings=_settings(llm_backend="openai"))
        assert isinstance(checker._client, OpenAILLMClient)

    def test_conversation_memory_uses_openai_client(self) -> None:
        from halle_gehirn.generator.memory import ConversationMemory

        memory = ConversationMemory(settings=_settings(llm_backend="openai"))
        assert isinstance(memory._client, OpenAILLMClient)

    def test_stages_use_ollama_client_by_default(self) -> None:
        from halle_gehirn.retrieval.query_rewriter import QueryRewriter

        rewriter = QueryRewriter(settings=_settings(llm_backend="ollama"))
        assert isinstance(rewriter._client, OllamaLLMClient)


class TestHealthBackendAware:
    """Der /ready-Check prueft das aktive LLM-Backend."""

    @pytest.mark.asyncio
    async def test_check_llm_openai_backend(self) -> None:
        from halle_gehirn.api.routes import health

        with patch(
            "halle_gehirn.api.routes.health._check_openai",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_openai, patch(
            "halle_gehirn.api.routes.health._check_ollama",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_ollama:
            ok = await health._check_llm(_settings(llm_backend="openai"))

        assert ok is True
        mock_openai.assert_awaited_once()
        mock_ollama.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_check_llm_ollama_backend(self) -> None:
        from halle_gehirn.api.routes import health

        with patch(
            "halle_gehirn.api.routes.health._check_openai",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_openai, patch(
            "halle_gehirn.api.routes.health._check_ollama",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_ollama:
            ok = await health._check_llm(_settings(llm_backend="ollama"))

        assert ok is True
        mock_ollama.assert_awaited_once()
        mock_openai.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_check_openai_missing_base_url_is_false(self) -> None:
        from halle_gehirn.api.routes.health import _check_openai

        assert await _check_openai("") is False
