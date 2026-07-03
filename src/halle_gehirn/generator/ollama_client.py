"""LLM-Client (qwen3), streaming -- Phase 5.

Wrapper um ollama.Client fuer Antwort-Generierung mit Streaming.
Think-Block (qwen3) wird NICHT unterdrueckt (Reasoning erwuenscht),
aber beim Streaming serverseitig gefiltert: nur Text nach </think>
geht an den Nutzer.

Verwendet sync ``ollama.Client`` + ``asyncio.Queue`` fuer
Windows-kompatibles Streaming (AsyncClient hat ConnectErrors).
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import ollama
import structlog

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.generator.prompts import build_messages

logger = structlog.get_logger(__name__)


class GeneratorError(Exception):
    """Fehler bei der Antwort-Generierung."""


class OllamaGenerator:
    """Streaming LLM-Generator via Ollama.

    Erzeugt Antworten Token-fuer-Token. Der qwen3-Think-Block wird
    beim Streaming gefiltert (State-Machine: alles zwischen <think>
    und </think> wird verworfen).

    Args:
        settings: Optionale Settings-Instanz.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = ollama.Client(host=self._settings.ollama_url)
        self._model = self._settings.llm_model
        self._num_predict = self._settings.gen_num_predict
        self._temperature = self._settings.gen_temperature

    async def generate(
        self,
        query: str,
        hits: list[Any],
        confidence: str = "gruen",
        memory_messages: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[str]:
        """Streamt die Antwort-Tokens (Think-Block gefiltert).

        Args:
            query: Die Benutzeranfrage.
            hits: RetrievalHit-Objekte als Kontext.
            confidence: Ampelstufe ('gruen'/'gelb'/'rot').
            memory_messages: Optionale Conversation-History.

        Yields:
            Sichtbare Antwort-Tokens (ohne Think-Inhalt).

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

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str | BaseException | None] = asyncio.Queue()

        def _sync_stream() -> None:
            try:
                for chunk in self._client.chat(
                    model=self._model,
                    messages=messages,
                    stream=True,
                    think=True,
                    options={
                        "num_predict": self._num_predict,
                        "temperature": self._temperature,
                    },
                ):
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        loop.call_soon_threadsafe(queue.put_nowait, token)
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        loop.run_in_executor(None, _sync_stream)

        async for token in _filter_think_stream(queue):
            yield token

        logger.info("generate_stream_done", query=query[:80])

    async def generate_full(
        self,
        query: str,
        hits: list[Any],
        confidence: str = "gruen",
        memory_messages: list[dict[str, str]] | None = None,
    ) -> str:
        """Generiert die komplette Antwort (nicht-streaming).

        Sammelt alle Tokens und gibt den vollstaendigen Text zurueck.
        Nuetzlich fuer Grounding/Validation nach der Generierung.

        Args:
            query: Die Benutzeranfrage.
            hits: RetrievalHit-Objekte als Kontext.
            confidence: Ampelstufe.
            memory_messages: Optionale Conversation-History.

        Returns:
            Vollstaendiger Antwort-Text (ohne Think-Block).
        """
        parts: list[str] = []
        async for token in self.generate(
            query, hits, confidence, memory_messages,
        ):
            parts.append(token)
        return "".join(parts)


async def _filter_think_stream(
    queue: asyncio.Queue[str | BaseException | None],
) -> AsyncIterator[str]:
    """Filtert <think>-Bloecke aus dem Token-Stream.

    State-Machine:
    - Puffert Tokens bis klar ist ob ein Think-Block vorliegt
    - Verwirft alles zwischen <think> und </think>
    - Yieldet nur sichtbare Tokens nach dem Think-Block

    Args:
        queue: Token-Queue aus dem Sync-Stream-Thread.

    Yields:
        Gefilterte Antwort-Tokens.
    """
    buffer = ""
    in_think = False
    think_done = False

    while True:
        item = await queue.get()
        if item is None:
            break
        if isinstance(item, BaseException):
            raise GeneratorError(str(item)) from item

        buffer += item

        # Noch im Think-Block?
        if in_think:
            end_pos = buffer.find("</think>")
            if end_pos != -1:
                # Think-Block beendet, Rest nach </think> yielden
                after = buffer[end_pos + len("</think>"):]
                buffer = ""
                in_think = False
                think_done = True
                cleaned = after.lstrip()
                if cleaned:
                    yield cleaned
            continue

        # Think-Block noch nicht abgeschlossen: pruefen
        if not think_done:
            # Warten bis genug Zeichen da sind um <think> zu erkennen
            if len(buffer) < 7:
                continue
            if buffer.lstrip().startswith("<think>"):
                in_think = True
                # Alles ab <think> im Puffer behalten
                think_start = buffer.find("<think>")
                buffer = buffer[think_start + len("<think>"):]
                # Pruefen ob </think> schon im Puffer
                end_pos = buffer.find("</think>")
                if end_pos != -1:
                    after = buffer[end_pos + len("</think>"):]
                    buffer = ""
                    in_think = False
                    think_done = True
                    cleaned = after.lstrip()
                    if cleaned:
                        yield cleaned
                continue
            # Kein Think-Block — alles yielden
            think_done = True
            yield buffer
            buffer = ""
            continue

        # Think bereits abgehandelt — direkt yielden
        yield buffer
        buffer = ""

    # Rest im Puffer
    if buffer and not in_think:
        yield buffer
