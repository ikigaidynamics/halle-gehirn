"""Query-Pipeline-Ausfuehrung -- Phase 6.

Fuehrt die 10 Pipeline-Stages in exakter Reihenfolge aus:
1. Smalltalk-Detection (0ms, kein LLM)
2. Guardrails (Injection-Check)
3. Router
4. Query-Transform (optional)
5. Retrieve (HybridRetriever)
6. Confidence-Gate (rot -> Refusal, KEIN LLM)
7. Generate (Streaming oder Full)
8. Validation (URL-Whitelist + Citation)
9. Grounding (Faithfulness-Check)
10. Audit (immer letzter Schritt)

WICHTIG: Guardrails VOR Retrieve, Confidence VOR Generate, Audit LAST.
"""
from __future__ import annotations

import hashlib
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import structlog

from halle_gehirn.generator.memory import ConversationMemory
from halle_gehirn.generator.smalltalk import get_response, is_smalltalk
from halle_gehirn.pipeline.factory import QueryPipeline
from halle_gehirn.pipeline.stages.grounding import GroundingResult
from halle_gehirn.pipeline.stages.validation import ValidationResult

logger = structlog.get_logger(__name__)


@dataclass
class QueryResult:
    """Ergebnis eines vollstaendigen Pipeline-Durchlaufs."""

    answer: str
    confidence: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0
    smalltalk: bool = False
    guardrail_blocked: bool = False
    guardrail_reason: str = ""
    query_type: str = ""
    validation: ValidationResult | None = None
    grounding: GroundingResult | None = None
    debug_info: dict[str, Any] = field(default_factory=dict)


class QueryOrchestrator:
    """Orchestriert die Query-Pipeline.

    Verwaltet per-Session ConversationMemory und fuehrt die
    10 Pipeline-Stages in der definierten Reihenfolge aus.

    Args:
        pipeline: Die gebaute QueryPipeline.
    """

    def __init__(self, pipeline: QueryPipeline) -> None:
        self._pipeline = pipeline
        self._sessions: dict[str, ConversationMemory] = {}

    def _get_memory(self, session_id: str) -> ConversationMemory:
        """Liefert oder erstellt ConversationMemory fuer eine Session."""
        if session_id not in self._sessions:
            self._sessions[session_id] = ConversationMemory(
                settings=self._pipeline.settings,
            )
        return self._sessions[session_id]

    async def run(
        self,
        query: str,
        session_id: str = "",
        filters: dict[str, Any] | None = None,
        debug: bool = False,
    ) -> QueryResult:
        """Fuehrt die komplette Pipeline aus (nicht-streaming).

        Args:
            query: Die Benutzeranfrage.
            session_id: Optionale Session-ID fuer Memory.
            filters: Optionale Qdrant-Filter.
            debug: Debug-Infos in Result aufnehmen.

        Returns:
            QueryResult mit Antwort, Konfidenz, Quellen.
        """
        start = time.monotonic()
        p = self._pipeline
        debug_info: dict[str, Any] = {}

        # 1. Smalltalk
        if is_smalltalk(query):
            answer = get_response(query)
            result = QueryResult(
                answer=answer,
                smalltalk=True,
                latency_ms=_elapsed_ms(start),
            )
            self._audit(query, result, session_id)
            return result

        # 2. Guardrails (VOR Retrieve)
        guard = p.guardrail.check_input(query)
        if not guard.approved:
            result = QueryResult(
                answer="Diese Anfrage kann ich leider nicht verarbeiten.",
                guardrail_blocked=True,
                guardrail_reason=guard.reason,
                latency_ms=_elapsed_ms(start),
            )
            self._audit(query, result, session_id)
            return result

        # 3. Router
        query_type = p.router.route(query)
        if debug:
            debug_info["query_type"] = query_type

        # 4. Query-Transform
        queries = await p.query_transformer.transform(query)
        if debug:
            debug_info["transformed_queries"] = queries

        # 5. Retrieve
        hits = await self._retrieve_dedup(queries, filters)
        if debug:
            debug_info["retrieval_hits"] = len(hits)

        # 6. Confidence-Gate (VOR Generate)
        confidence = p.confidence_gate.assess(hits)
        if debug:
            debug_info["confidence"] = confidence

        # 7. Generate (non-streaming)
        memory = self._get_memory(session_id) if session_id else None
        memory_msgs = memory.get_messages() if memory else None
        answer = await p.generator.generate_full(
            query=query,
            hits=hits,
            confidence=confidence,
            memory_messages=memory_msgs,
        )

        # Memory aktualisieren
        if memory:
            memory.add_turn("user", query)
            memory.add_turn("assistant", answer)
            await memory.summarize_if_needed()

        # 8. Validation (URL-Whitelist + Citation)
        validation = p.validator.validate(answer, hits)
        answer = validation.cleaned_answer

        # 9. Grounding
        grounding = None
        if p.settings.use_grounding_check and confidence != "rot":
            grounding = await p.grounding_checker.check(answer, hits)

        # Output-Guardrails (PII-Redaktion)
        pii = p.guardrail.check_output(answer)
        if pii.reason:
            answer = p.guardrail.redact_pii(answer)

        sources = _build_sources(hits)
        result = QueryResult(
            answer=answer,
            confidence=confidence,
            sources=sources,
            latency_ms=_elapsed_ms(start),
            query_type=query_type,
            validation=validation,
            grounding=grounding,
            debug_info=debug_info if debug else {},
        )

        # 10. Audit (LAST)
        self._audit(query, result, session_id)
        return result

    async def run_stream(
        self,
        query: str,
        session_id: str = "",
        filters: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Fuehrt die Pipeline aus und streamt Token-Events.

        Yields SSE-kompatible Dicts:
        - {"type": "token", "content": "..."}
        - {"type": "done", "confidence": "...", "sources": [...]}

        Args:
            query: Die Benutzeranfrage.
            session_id: Optionale Session-ID fuer Memory.
            filters: Optionale Qdrant-Filter.

        Yields:
            SSE-Event-Dicts.
        """
        start = time.monotonic()
        p = self._pipeline

        # 1. Smalltalk
        if is_smalltalk(query):
            answer = get_response(query)
            yield {"type": "token", "content": answer}
            yield _done_event("", [], start)
            self._audit(
                query,
                QueryResult(answer=answer, smalltalk=True),
                session_id,
            )
            return

        # 2. Guardrails (VOR Retrieve)
        guard = p.guardrail.check_input(query)
        if not guard.approved:
            msg = "Diese Anfrage kann ich leider nicht verarbeiten."
            yield {"type": "token", "content": msg}
            yield _done_event("", [], start)
            self._audit(
                query,
                QueryResult(answer=msg, guardrail_blocked=True),
                session_id,
            )
            return

        # 3. Router
        p.router.route(query)

        # 4. Query-Transform
        queries = await p.query_transformer.transform(query)

        # 5. Retrieve
        hits = await self._retrieve_dedup(queries, filters)

        # 6. Confidence-Gate (VOR Generate)
        confidence = p.confidence_gate.assess(hits)

        # 7. Generate (STREAMING)
        memory = self._get_memory(session_id) if session_id else None
        memory_msgs = memory.get_messages() if memory else None
        parts: list[str] = []

        async for token in p.generator.generate(
            query=query,
            hits=hits,
            confidence=confidence,
            memory_messages=memory_msgs,
        ):
            parts.append(token)
            yield {"type": "token", "content": token}

        full_answer = "".join(parts)

        # Memory aktualisieren
        if memory:
            memory.add_turn("user", query)
            memory.add_turn("assistant", full_answer)
            await memory.summarize_if_needed()

        # 8. Validation (post-generation, nicht gestreamt)
        p.validator.validate(full_answer, hits)

        # 9. Grounding (post-generation)
        if p.settings.use_grounding_check and confidence != "rot":
            await p.grounding_checker.check(full_answer, hits)

        # Output-Guardrails
        p.guardrail.check_output(full_answer)

        sources = _build_sources(hits)

        # Done-Event mit Metadaten
        yield _done_event(confidence, sources, start)

        # 10. Audit (LAST)
        self._audit(
            query,
            QueryResult(
                answer=full_answer,
                confidence=confidence,
                sources=sources,
            ),
            session_id,
        )

    async def _retrieve_dedup(
        self,
        queries: list[str],
        filters: dict[str, Any] | None,
    ) -> list[Any]:
        """Retrieval ueber alle Queries mit Deduplizierung."""
        all_hits: list[Any] = []
        for q in queries:
            hits = await self._pipeline.retriever.retrieve(
                q, filters=filters,
            )
            all_hits.extend(hits)
        return _deduplicate_hits(all_hits)

    def _audit(
        self, query: str, result: QueryResult, session_id: str,
    ) -> None:
        """Schreibt den Audit-Eintrag (immer letzter Schritt)."""
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        source_ids = [s.get("id", "") for s in result.sources]
        self._pipeline.audit_logger.log({
            "query_hash": query_hash,
            "confidence": result.confidence,
            "source_ids": source_ids,
            "latency_ms": round(result.latency_ms, 1),
            "guardrail_blocked": result.guardrail_blocked,
            "smalltalk": result.smalltalk,
            "session_id": session_id,
        })

    def clear_session(self, session_id: str) -> None:
        """Loescht die Memory einer Session."""
        self._sessions.pop(session_id, None)


def _elapsed_ms(start: float) -> float:
    """Berechnet die vergangene Zeit in Millisekunden."""
    return (time.monotonic() - start) * 1000


def _done_event(
    confidence: str,
    sources: list[dict[str, Any]],
    start: float,
) -> dict[str, Any]:
    """Baut das finale Done-SSE-Event."""
    return {
        "type": "done",
        "confidence": confidence,
        "sources": sources,
        "latency_ms": round(_elapsed_ms(start), 1),
    }


def _deduplicate_hits(hits: list[Any]) -> list[Any]:
    """Dedupliziert Treffer nach point_id, behaelt hoechsten Score."""
    seen: dict[str, Any] = {}
    for hit in hits:
        pid = hit.point_id
        if pid not in seen or hit.rerank_score > seen[pid].rerank_score:
            seen[pid] = hit
    deduped = list(seen.values())
    deduped.sort(key=lambda h: h.rerank_score, reverse=True)
    return deduped


def _build_sources(hits: list[Any]) -> list[dict[str, Any]]:
    """Baut Source-Dicts aus RetrievalHits."""
    sources: list[dict[str, Any]] = []
    for i, hit in enumerate(hits, start=1):
        payload = getattr(hit, "payload", {}) or {}
        sources.append({
            "id": f"S{i}",
            "titel": payload.get("titel", "Unbekannt"),
            "url": payload.get("source_url"),
            "snippet": (payload.get("text", ""))[:200],
            "page": payload.get("page"),
            "score": round(hit.rerank_score, 4),
        })
    return sources
