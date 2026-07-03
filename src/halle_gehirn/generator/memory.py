"""Conversation-Window + Summarization -- Phase 5.

Multi-Turn Memory: Window der letzten N Turns + optionale
LLM-Summarization fuer aeltere Turns. State ist In-Memory
(Persistence kommt mit der API in Phase 6).
"""
from __future__ import annotations

import asyncio

import ollama
import structlog

from halle_gehirn.config import Settings, get_settings

logger = structlog.get_logger(__name__)

_SUMMARY_PROMPT = """\
Fasse das folgende Gespraech in 2-3 Saetzen zusammen. \
Behalte die wichtigsten Fakten und Fragen bei. \
Antworte NUR mit der Zusammenfassung.

Gespraech:
{conversation}"""


class ConversationMemory:
    """In-Memory Conversation Window mit optionaler Summarization.

    Speichert die letzten N Turns (MEMORY_WINDOW) als Message-Dicts.
    Aeltere Turns werden optional via LLM zusammengefasst
    (USE_SUMMARY_MEMORY).

    Args:
        settings: Optionale Settings-Instanz.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._turns: list[dict[str, str]] = []
        self._summary: str = ""
        self._client = ollama.Client(host=self._settings.ollama_url)

    def add_turn(self, role: str, content: str) -> None:
        """Fuegt einen Turn hinzu.

        Args:
            role: 'user' oder 'assistant'.
            content: Der Nachrichteninhalt.
        """
        self._turns.append({"role": role, "content": content})

    def get_messages(self) -> list[dict[str, str]]:
        """Liefert die Conversation-History fuer den LLM-Aufruf.

        Gibt die letzten MEMORY_WINDOW Turns zurueck, optional mit
        vorangestellter Zusammenfassung aelterer Turns.

        Returns:
            Liste von Message-Dicts (role/content).
        """
        window = self._settings.memory_window * 2  # user+assistant = 1 Turn
        recent = self._turns[-window:] if len(self._turns) > window else self._turns

        messages: list[dict[str, str]] = []
        if self._summary:
            messages.append({
                "role": "system",
                "content": f"Bisheriges Gespraech (Zusammenfassung): {self._summary}",
            })
        messages.extend(recent)
        return messages

    async def summarize_if_needed(self) -> None:
        """Fasst aeltere Turns zusammen, wenn das Window ueberschritten wird.

        Nur aktiv wenn USE_SUMMARY_MEMORY=true und genug Turns vorhanden.
        """
        if not self._settings.use_summary_memory:
            return

        window = self._settings.memory_window * 2
        if len(self._turns) <= window:
            return

        # Aeltere Turns extrahieren
        overflow = self._turns[:-window]
        if not overflow:
            return

        conversation = "\n".join(
            f"{t['role']}: {t['content']}" for t in overflow
        )
        prompt = _SUMMARY_PROMPT.format(conversation=conversation[:3000])

        try:
            response = await asyncio.to_thread(
                self._client.chat,
                model=self._settings.llm_model,
                messages=[{"role": "user", "content": prompt}],
                think=False,
                options={"temperature": 0.0, "num_predict": 256},
            )
            self._summary = response["message"]["content"].strip()
            # Overflow entfernen, nur Window behalten
            self._turns = self._turns[-window:]
            logger.info(
                "memory_summarized",
                overflow_turns=len(overflow),
                summary_len=len(self._summary),
            )
        except Exception as exc:
            logger.warning("memory_summarize_failed", error=str(exc))

    def clear(self) -> None:
        """Setzt Memory zurueck."""
        self._turns.clear()
        self._summary = ""

    @property
    def turn_count(self) -> int:
        """Anzahl gespeicherter Turns."""
        return len(self._turns)
