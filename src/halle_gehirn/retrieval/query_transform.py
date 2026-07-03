"""HyDE/Multi-Query/Decomposition — Phase 4.

Transformiert die Benutzeranfrage in mehrere Suchvarianten, um den
Recall zu erhoehen. Nur aktiv wenn USE_QUERY_TRANSFORM=true.

Strategien:
- Multi-Query: LLM generiert 3 Reformulierungen der Anfrage.
- HyDE (Hypothetical Document Embeddings): LLM generiert ein
  hypothetisches Antwortdokument, das als Suchvektor dient.
"""
from __future__ import annotations

import asyncio
import re

import ollama
import structlog

from halle_gehirn.config import Settings, get_settings

logger = structlog.get_logger(__name__)

_MULTI_QUERY_PROMPT = """\
/no_think
Generiere genau 3 alternative Formulierungen der folgenden Frage, \
um verschiedene Aspekte abzudecken. Jede Variante auf einer eigenen Zeile. \
Antworte NUR mit den 3 Zeilen, ohne Nummerierung oder Erklaerung.

Frage: {query}"""

_HYDE_PROMPT = """\
/no_think
Schreibe einen kurzen Absatz (3-5 Saetze), der die folgende Frage \
sachlich und praezise beantwortet. Formuliere so, als waere es ein \
Auszug aus einem Fachhandbuch. Antworte NUR mit dem Absatz.

Frage: {query}"""


class QueryTransformError(Exception):
    """Fehler bei der Query-Transformation."""


class OllamaQueryTransformer:
    """Query-Transformer via Ollama (Multi-Query + HyDE).

    Erzeugt alternative Anfrage-Varianten, um den Recall bei der
    Hybrid-Suche zu erhoehen. Deaktivierbar per Config.

    Verwendet sync ``ollama.Client`` + ``asyncio.to_thread()``
    (gleicher Ansatz wie OllamaEmbedder/LogprobsReranker).

    Args:
        settings: Optionale Settings-Instanz.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = ollama.Client(host=self._settings.ollama_url)
        self._model = self._settings.llm_model

    async def transform(self, query: str) -> list[str]:
        """Erzeugt alternative Anfragen (Original + Varianten).

        Args:
            query: Die originale Benutzeranfrage.

        Returns:
            Liste mit der originalen + transformierten Anfragen.
            Bei Fehler: nur die originale Anfrage.
        """
        if not self._settings.use_query_transform:
            return [query]

        queries = [query]
        try:
            variants = await self._multi_query(query)
            queries.extend(variants)
        except Exception as exc:
            logger.warning(
                "multi_query_failed",
                error=str(exc),
            )

        logger.info(
            "query_transform_done",
            original=query,
            total=len(queries),
        )
        return queries

    async def _multi_query(self, query: str) -> list[str]:
        """Generiert 3 alternative Formulierungen."""
        prompt = _MULTI_QUERY_PROMPT.format(query=query)
        response = await asyncio.to_thread(
            self._client.chat,
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.7, "num_predict": 512},
        )
        content: str = response["message"]["content"].strip()
        content = _strip_think_tags(content)
        lines = [
            _clean_line(line)
            for line in content.split("\n")
            if _clean_line(line)
        ]
        return lines[:3]

    async def hyde(self, query: str) -> str:
        """Generiert ein hypothetisches Antwortdokument (HyDE).

        Args:
            query: Die Benutzeranfrage.

        Returns:
            Hypothetischer Antworttext.
        """
        prompt = _HYDE_PROMPT.format(query=query)
        response = await asyncio.to_thread(
            self._client.chat,
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.3, "num_predict": 512},
        )
        content: str = response["message"]["content"].strip()
        return _strip_think_tags(content)


def _clean_line(line: str) -> str:
    """Entfernt Nummerierungen und Whitespace."""
    cleaned = re.sub(r"^\d+[.)]\s*", "", line.strip())
    cleaned = re.sub(r"^[-*]\s*", "", cleaned)
    return cleaned.strip()


def _strip_think_tags(text: str) -> str:
    """Extrahiert die Antwort nach <think>-Block (qwen3)."""
    if "<think>" not in text:
        return text.strip()
    match = re.search(r"</think>\s*(.*)", text, flags=re.DOTALL)
    if match and match.group(1).strip():
        return match.group(1).strip()
    inner = re.search(r"<think>(.*?)</think>", text, flags=re.DOTALL)
    if inner and inner.group(1).strip():
        return inner.group(1).strip()
    return ""
