"""Contextual Retrieval — per-Chunk Kontext-Anreicherung via LLM.

Erzeugt fuer jeden Chunk einen knappen Kontextsatz, der den Chunk im
Gesamtdokument einordnet (Anthropic Contextual Retrieval). Dieser wird
als ``context_prefix`` vor dem Embedding vorangestellt (+5-15% Recall).

Laeuft concurrent mit Semaphore (CONTEXT_CONCURRENCY). Deaktivierbar
ueber USE_CONTEXTUAL_RETRIEVAL=false.
"""
from __future__ import annotations

import asyncio
import re

import ollama
import structlog

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.extraction.base import ExtractedDoc
from halle_gehirn.pipeline.chunker import Chunk

logger = structlog.get_logger(__name__)

# /no_think unterdrueckt den <think>-Block bei qwen3-Modellen
_CONTEXT_PROMPT = """\
/no_think
<document>
{doc_title}

{doc_summary}
</document>

Hier ist der Chunk, den wir im Gesamtdokument einordnen wollen:
<chunk>
{chunk_text}
</chunk>

Gib einen kurzen, praegnanten Kontext-Satz (1-2 Saetze, maximal 100 Woerter), \
der diesen Chunk im Gesamtdokument einordnet. Antworte NUR mit dem Kontext-Satz, \
ohne Erklaerung oder Prafix."""

# Kurzfassungs-/Abstract-Heading im Body — beste Quelle fuer die Doc-Summary
_SUMMARY_HEADING_RE = re.compile(
    r"^#{1,6}\s+(kurzfassung|abstract|zusammenfassung|summary)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_SUMMARY_MAX_CHARS = 800


def build_doc_summary(body_md: str, max_chars: int = _SUMMARY_MAX_CHARS) -> str:
    """Baut die Dokument-Zusammenfassung fuer den Kontext-Prompt.

    Bevorzugt den Kurzfassungs-/Abstract-Abschnitt (bei Abschlussarbeiten
    die dichteste Selbstbeschreibung); Fallback: Dokumentanfang.

    Args:
        body_md: Body-Markdown des Dokuments.
        max_chars: Maximale Laenge der Zusammenfassung.

    Returns:
        Zusammenfassungs-Text (max. *max_chars* Zeichen).
    """
    match = _SUMMARY_HEADING_RE.search(body_md)
    if match:
        return body_md[match.start() : match.start() + max_chars]
    return body_md[:max_chars]


class OllamaContextEnricher:
    """Contextual-Retrieval-Enricher via Ollama.

    Erzeugt per Chunk einen Kontext-Satz ueber das konfigurierte LLM.
    Concurrent mit Semaphore begrenzt auf CONTEXT_CONCURRENCY.

    Args:
        settings: Optionale Settings-Instanz.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = ollama.AsyncClient(host=self._settings.ollama_url)
        self._model = self._settings.llm_model
        self._semaphore = asyncio.Semaphore(self._settings.context_concurrency)

    async def enrich(
        self, chunks: list[Chunk], doc: ExtractedDoc,
    ) -> list[Chunk]:
        """Reichert Chunks um context_prefix an.

        Args:
            chunks: Liste von Chunks (werden in-place modifiziert).
            doc: Das zugehoerige ExtractedDoc (fuer Titel/Zusammenfassung).

        Returns:
            Dieselbe Chunk-Liste mit gesetztem context_prefix.
        """
        if not self._settings.use_contextual_retrieval:
            logger.info("context_enrichment_skipped", reason="disabled")
            return chunks
        if not chunks:
            return chunks

        doc_summary = build_doc_summary(doc.body_md)
        tasks = [
            self._enrich_single(chunk, doc.title, doc_summary)
            for chunk in chunks
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success = 0
        failures = 0
        for chunk, result in zip(chunks, results, strict=True):
            if isinstance(result, str) and result:
                chunk.context_prefix = result
                success += 1
            elif isinstance(result, Exception):
                failures += 1
                logger.debug(
                    "context_enrich_failed",
                    chunk_index=chunk.chunk_index,
                    error=str(result),
                )
        if failures and success == 0:
            # Ollama komplett nicht erreichbar — eine Warnung statt N
            logger.warning(
                "context_enrichment_unavailable",
                source=doc.source,
                chunks=len(chunks),
                sample_error=str(
                    next(r for r in results if isinstance(r, Exception))
                ),
            )
        logger.info(
            "context_enrichment_done",
            total=len(chunks),
            success=success,
            failures=failures,
        )
        return chunks

    async def _enrich_single(
        self, chunk: Chunk, doc_title: str, doc_summary: str,
    ) -> str:
        """Erzeugt Kontext-Satz fuer einen einzelnen Chunk."""
        async with self._semaphore:
            prompt = _CONTEXT_PROMPT.format(
                doc_title=doc_title,
                doc_summary=doc_summary,
                chunk_text=chunk.text[:1000],
            )
            response = await self._client.chat(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.0, "num_predict": 512},
            )
            content: str = response["message"]["content"].strip()
            content = _strip_think_tags(content)
            return content


from halle_gehirn.llm_utils import strip_think_tags as _strip_think_tags  # noqa: E402
