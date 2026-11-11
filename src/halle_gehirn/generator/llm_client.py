"""Backend-abhaengiger LLM-Client (non-streaming) -- Factory.

Einheitliche Sync-Schnittstelle ``chat()`` fuer interne LLM-Stages
(QueryRewriter, FaithfulnessChecker, ConversationMemory, QueryTransformer),
die kein Streaming brauchen. Antwortformat ist Ollama-Shape
``{"message": {"content": ...}}``, damit Aufrufer backend-agnostisch bleiben.

Auswahl ueber ``llm_backend`` in der Config (factory-Pattern wie bei
Generator/Reranker/Embedder).
"""
from __future__ import annotations

from typing import Any, Protocol, cast, runtime_checkable

import httpx
import ollama
import structlog

from halle_gehirn.config import Settings, get_settings

logger = structlog.get_logger(__name__)

_TIMEOUT = 60.0


@runtime_checkable
class LLMClient(Protocol):
    """Sync-LLM-Client mit Ollama-Antwortformat."""

    @property
    def model(self) -> str:
        """Aktives LLM-Modell (backend-abhaengig aufgelöst)."""
        ...

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
        think: bool = True,
    ) -> dict[str, Any]:
        """Nicht-streamender Chat-Call.

        Args:
            model: Modellname.
            messages: Chat-Messages (role/content).
            options: ``temperature`` und ``num_predict``.
            think: Think-Block deaktivieren (nur Ollama-Unterstützung).

        Returns:
            Dict mit ``{"message": {"content": str}}`` (Ollama-Shape).
        """
        ...


class OllamaLLMClient:
    """Sync-LLM-Client via Ollama (Wrapper um ``ollama.Client``)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = ollama.Client(host=self._settings.ollama_url)
        self._model = self._settings.llm_model

    @property
    def model(self) -> str:
        """Ollama-LLM-Modell."""
        return self._model

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
        think: bool = True,
    ) -> dict[str, Any]:
        """Chat-Call via Ollama (ChatResponse ist dict-subskriptierbar)."""
        response = self._client.chat(
            model=model,
            messages=messages,
            think=think,
            options=options,
        )
        return cast(dict[str, Any], response)


class OpenAILLMClient:
    """Sync-LLM-Client via OpenAI-kompatibler API (vLLM, TEI, llama.cpp).

    Antwort wird in das Ollama-Shape ``{"message": {"content": ...}}``
    uebersetzt, damit Aufrufer unveraendert bleiben.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        base_url = self._settings.openai_base_url.rstrip("/")
        if not base_url:
            raise ValueError(
                "llm_backend=openai erfordert OPENAI_BASE_URL in der Config."
            )
        self._base_url = base_url
        self._api_key = self._settings.openai_api_key or "no-key"
        self._model = self._settings.openai_model or self._settings.llm_model

    @property
    def model(self) -> str:
        """OpenAI-LLM-Modell (openai_model, sonst llm_model)."""
        return self._model

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
        think: bool = True,
    ) -> dict[str, Any]:
        """Chat-Call via OpenAI-Chat-Completions (non-streaming).

        ``think`` wird ignoriert: Think-Blockkontrolle ist serverseitig
        nicht standardisiert; Aufrufer entfernen Think-Tags selbst
        (``strip_think_tags``).
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if options:
            if "num_predict" in options:
                payload["max_tokens"] = options["num_predict"]
            if "temperature" in options:
                payload["temperature"] = options["temperature"]

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        response = httpx.post(
            url, json=payload, headers=headers, timeout=_TIMEOUT,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"OpenAI LLM error {response.status_code}: "
                f"{response.text[:200]}"
            )
        data: dict[str, Any] = response.json()
        content = data["choices"][0]["message"].get("content", "")
        return {"message": {"content": content}}


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    """Fabrikt den LLM-Client gemäss ``llm_backend``.

    Args:
        settings: Optionale Settings-Instanz.

    Returns:
        OllamaLLMClient oder OpenAILLMClient.
    """
    s = settings or get_settings()
    if s.llm_backend == "openai":
        return OpenAILLMClient(settings=s)
    return OllamaLLMClient(settings=s)
