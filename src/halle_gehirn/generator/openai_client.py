"""LLM-Client (OpenAI-kompatibel), streaming.

Wrapper fuer OpenAI-kompatible APIs (vLLM, text-generation-inference, etc.).
Implementiert dieselbe Schnittstelle wie OllamaGenerator.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import structlog

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.generator.prompts import build_messages

logger = structlog.get_logger(__name__)


class GeneratorError(Exception):
    """Fehler bei der Antwort-Generierung."""


class OpenAIGenerator:
    """Streaming LLM-Generator via OpenAI-kompatible API.

    Unterstuetzt vLLM, text-generation-inference, und andere Server,
    die das OpenAI-Chat-Completions-Format implementieren.

    Args:
        settings: Optionale Settings-Instanz.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._base_url = self._settings.openai_base_url.rstrip("/")
        self._api_key = self._settings.openai_api_key or "no-key"
        self._model = self._settings.openai_model or self._settings.llm_model
        self._num_predict = self._settings.gen_num_predict
        self._temperature = self._settings.gen_temperature

    async def generate(
        self,
        query: str,
        hits: list[Any],
        confidence: str = "gruen",
        memory_messages: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[str]:
        """Streamt die Antwort-Tokens.

        Args:
            query: Die Benutzeranfrage.
            hits: RetrievalHit-Objekte als Kontext.
            confidence: Ampelstufe ('gruen'/'gelb'/'rot').
            memory_messages: Optionale Conversation-History.

        Yields:
            Antwort-Tokens.

        Raises:
            GeneratorError: Bei Verbindungsfehlern.
        """
        messages = build_messages(
            query=query,
            hits=hits,
            memory_messages=memory_messages,
            confidence=confidence,
            contact_url=self._settings.contact_fallback_url,
        )

        # Refusal: letzter Assistant-Msg ist das Refusal-Template
        if confidence == "rot" or not hits:
            assistant_msgs = [
                m for m in messages if m["role"] == "assistant"
            ]
            if assistant_msgs:
                yield assistant_msgs[-1]["content"]
            return

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "max_tokens": self._num_predict,
            "temperature": self._temperature,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST", url, json=payload, headers=headers,
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        raise GeneratorError(
                            f"OpenAI API error {response.status_code}: {error_text}"
                        )

                    buffer = ""
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break
                            try:
                                import json
                                chunk = json.loads(data)
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    # Think-Block filtern (falls vorhanden)
                                    async for token in self._filter_think(
                                        content, buffer,
                                    ):
                                        yield token
                            except (json.JSONDecodeError, IndexError, KeyError):
                                continue

        except httpx.RequestError as exc:
            raise GeneratorError(f"Connection error: {exc}") from exc

        logger.info("generate_stream_done", query=query[:80])

    async def _filter_think(
        self, content: str, buffer: str,
    ) -> AsyncIterator[str]:
        """Filtert <think>-Bloecke aus dem Content.

        Einfache Variante: entfernt alles zwischen <think> und </think>.
        """
        # Einfache Implementierung: Think-Tags entfernen
        import re
        # Entferne komplette Think-Bloecke
        cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
        # Entferne unvollstaendige oeffnende Tags am Ende
        cleaned = re.sub(r"<think>.*$", "", cleaned, flags=re.DOTALL)
        if cleaned:
            yield cleaned

    async def generate_full(
        self,
        query: str,
        hits: list[Any],
        confidence: str = "gruen",
        memory_messages: list[dict[str, str]] | None = None,
    ) -> str:
        """Generiert die komplette Antwort (nicht-streaming).

        Sammelt alle Tokens und gibt den vollstaendigen Text zurueck.

        Args:
            query: Die Benutzeranfrage.
            hits: RetrievalHit-Objekte als Kontext.
            confidence: Ampelstufe.
            memory_messages: Optionale Conversation-History.

        Returns:
            Vollstaendiger Antwort-Text.
        """
        parts: list[str] = []
        async for token in self.generate(
            query, hits, confidence, memory_messages,
        ):
            parts.append(token)
        return "".join(parts)
