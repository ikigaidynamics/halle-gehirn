"""Query-Pipeline-Ausfuehrung -- Phase 6.

Fuehrt die Pipeline-Stages in exakter Reihenfolge aus:
1. Smalltalk-Detection (0ms, kein LLM)
2. Guardrails (Injection-Check)
3. Query-Rewrite (konversationell → eigenstaendig)
4. Router
5. Query-Transform (optional)
6. Retrieve (HybridRetriever)
7. Confidence-Gate (rot -> Refusal, KEIN LLM)
8. Generate (Streaming oder Full)
9. Validation (URL-Whitelist + Citation)
10. Grounding (Faithfulness-Check)
11. Retrieval-Log (JSONL, Debugging)
12. Audit (immer letzter Schritt)

WICHTIG: Guardrails VOR Retrieve, Confidence VOR Generate, Audit LAST.
"""
from __future__ import annotations

import hashlib
import re
import time
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import structlog

from halle_gehirn.generator.memory import ConversationMemory
from halle_gehirn.generator.smalltalk import get_response, is_smalltalk
from halle_gehirn.observability.retrieval_logger import (
    PipelineTimer,
    build_log_entry,
)
from halle_gehirn.pipeline.factory import QueryPipeline
from halle_gehirn.pipeline.stages.grounding import GroundingResult
from halle_gehirn.pipeline.stages.validation import ValidationResult
from halle_gehirn.retrieval.query_rewriter import RewriteResult

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
    pii_redacted: bool = False
    debug_info: dict[str, Any] = field(default_factory=dict)


@dataclass
class _FinalizedAnswer:
    """Ergebnis der Post-Generation-Stages (8 Validation, 9 Grounding, PII).

    Gemeinsamer Rueckgabetyp fuer run() und run_stream() — garantiert,
    dass beide Pfade dieselben Anti-Halluzinations-/PII-Stufen anwenden.
    """

    answer: str
    validation: ValidationResult | None = None
    grounding: GroundingResult | None = None
    pii_redacted: bool = False


class QueryOrchestrator:
    """Orchestriert die Query-Pipeline.

    Verwaltet per-Session ConversationMemory und fuehrt die
    10 Pipeline-Stages in der definierten Reihenfolge aus.

    Args:
        pipeline: Die gebaute QueryPipeline.
    """

    # Obergrenze gehaltener Session-Memories (LRU-Eviction)
    _MAX_SESSIONS = 500

    def __init__(self, pipeline: QueryPipeline) -> None:
        self._pipeline = pipeline
        self._sessions: OrderedDict[str, ConversationMemory] = OrderedDict()

    def _get_memory(self, session_id: str) -> ConversationMemory:
        """Liefert oder erstellt ConversationMemory fuer eine Session.

        LRU-Eviction: haelt maximal _MAX_SESSIONS Memories — sonst
        waechst das Dict mit jeder je gesehenen Session-ID unbegrenzt.
        """
        if session_id in self._sessions:
            self._sessions.move_to_end(session_id)
            return self._sessions[session_id]
        if len(self._sessions) >= self._MAX_SESSIONS:
            evicted, _ = self._sessions.popitem(last=False)
            logger.info("session_memory_evicted", session_id=evicted)
        memory = ConversationMemory(settings=self._pipeline.settings)
        self._sessions[session_id] = memory
        return memory

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
        timer = PipelineTimer()
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

        # Memory einmal holen (fuer Rewrite UND Generator)
        memory = self._get_memory(session_id) if session_id else None

        # 3. Query-Rewrite (konversationell → eigenstaendig)
        rewrite_result: RewriteResult | None = None
        search_query = query
        if p.settings.use_query_rewrite:
            timer.start("rewrite")
            history = memory.get_messages() if memory else []
            rewrite_result = await p.query_rewriter.rewrite(query, history)
            search_query = rewrite_result.rewritten
            timer.stop("rewrite")
        if debug and rewrite_result:
            debug_info["query_rewritten"] = rewrite_result.rewritten
            debug_info["was_rewritten"] = rewrite_result.was_rewritten

        # 4. Router (nutzt rewritten query)
        query_type = p.router.route(search_query)
        if debug:
            debug_info["query_type"] = query_type

        # 5. Query-Transform (nutzt rewritten query)
        queries = await p.query_transformer.transform(search_query)
        if debug:
            debug_info["transformed_queries"] = queries

        # 6. Retrieve (Timer fuer embed/search/rerank intern)
        hits = await self._retrieve_dedup(queries, filters, timer)
        if debug:
            debug_info["retrieval_hits"] = len(hits)

        # 7. Confidence-Gate (VOR Generate)
        confidence = p.confidence_gate.assess(hits)
        if debug:
            debug_info["confidence"] = confidence

        # 8. Generate (non-streaming, ORIGINAL query an Generator)
        memory_msgs = memory.get_messages() if memory else None
        timer.start("generate")
        answer = await p.generator.generate_full(
            query=query,
            hits=hits,
            confidence=confidence,
            memory_messages=memory_msgs,
        )
        timer.stop("generate")

        # 9./10. Validation + Grounding + PII (gemeinsam mit Stream-Pfad)
        final = await self._finalize_answer(answer, hits, confidence)

        # Memory aktualisiert die BEREINIGTE Antwort (nicht den Rohtext)
        if memory:
            memory.add_turn("user", query)
            memory.add_turn("assistant", final.answer)
            await memory.summarize_if_needed()

        sources = _build_sources(hits)
        result = QueryResult(
            answer=final.answer,
            confidence=confidence,
            sources=sources,
            latency_ms=_elapsed_ms(start),
            query_type=query_type,
            validation=final.validation,
            grounding=final.grounding,
            pii_redacted=final.pii_redacted,
            debug_info=debug_info if debug else {},
        )

        # 11. Retrieval-Log (JSONL)
        self._log_retrieval(
            session_id=session_id,
            rewrite_result=rewrite_result,
            query_type=query_type,
            hits=hits,
            confidence=confidence,
            outcome=_outcome(confidence, result),
            answer_length=len(final.answer),
            timer=timer,
        )

        # 12. Audit (LAST)
        self._audit(query, result, session_id, rewrite_result)
        return result

    async def _finalize_answer(
        self,
        answer: str,
        hits: list[Any],
        confidence: str,
    ) -> _FinalizedAnswer:
        """Post-Generation-Stages: 8 Validation, 9 Grounding, PII-Redaktion.

        Gemeinsamer Pfad fuer run() und run_stream() — die Anti-
        Halluzinations- und PII-Stufen gelten fuer BEIDE Antwortwege.
        """
        p = self._pipeline

        # 8. Validation (URL-Whitelist + Citation)
        validation = p.validator.validate(answer, hits)
        cleaned = validation.cleaned_answer

        # 9. Grounding
        grounding = None
        if p.settings.use_grounding_check and confidence != "rot":
            grounding = await p.grounding_checker.check(cleaned, hits)

        # Output-Guardrails (PII-Redaktion)
        pii = p.guardrail.check_output(cleaned)
        pii_redacted = False
        if pii.reason:
            cleaned = p.guardrail.redact_pii(cleaned)
            pii_redacted = True

        return _FinalizedAnswer(
            answer=cleaned,
            validation=validation,
            grounding=grounding,
            pii_redacted=pii_redacted,
        )

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
        timer = PipelineTimer()

        # 1. Smalltalk
        if is_smalltalk(query):
            answer = get_response(query)
            yield {"type": "token", "content": answer}
            yield _done_event("", [], start, _FinalizedAnswer(answer=answer))
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
            yield _done_event("", [], start, _FinalizedAnswer(answer=msg))
            self._audit(
                query,
                QueryResult(answer=msg, guardrail_blocked=True),
                session_id,
            )
            return

        # Memory einmal holen (fuer Rewrite UND Generator)
        memory = self._get_memory(session_id) if session_id else None

        # 3. Query-Rewrite (konversationell → eigenstaendig)
        rewrite_result: RewriteResult | None = None
        search_query = query
        if p.settings.use_query_rewrite:
            timer.start("rewrite")
            history = memory.get_messages() if memory else []
            rewrite_result = await p.query_rewriter.rewrite(query, history)
            search_query = rewrite_result.rewritten
            timer.stop("rewrite")

        # 4. Router (nutzt rewritten query)
        p.router.route(search_query)

        # 5. Query-Transform (nutzt rewritten query)
        queries = await p.query_transformer.transform(search_query)

        # 6. Retrieve (Timer fuer embed/search/rerank intern)
        hits = await self._retrieve_dedup(queries, filters, timer)

        # 7. Confidence-Gate (VOR Generate)
        confidence = p.confidence_gate.assess(hits)

        # 8. Generate (STREAMING, ORIGINAL query an Generator)
        memory_msgs = memory.get_messages() if memory else None
        parts: list[str] = []

        timer.start("generate")
        async for token in p.generator.generate(
            query=query,
            hits=hits,
            confidence=confidence,
            memory_messages=memory_msgs,
        ):
            parts.append(token)
            yield {"type": "token", "content": token}
        timer.stop("generate")

        full_answer = "".join(parts)

        # Keepalive waehrend Post-Generation (Grounding-LLM-Aufruf
        # kann >30s dauern — ohne Daten-Fluss droht Client-Timeout)
        yield {"type": "status", "content": ""}

        # 9./10. Validation + Grounding + PII
        final = await self._finalize_answer(full_answer, hits, confidence)

        # Memory speichert die BEREINIGTE Antwort
        if memory:
            memory.add_turn("user", query)
            memory.add_turn("assistant", final.answer)
            await memory.summarize_if_needed()

        sources = _build_sources(hits)

        # Done-Event mit Metadaten + finaler (bereinigter) Antwort
        yield _done_event(confidence, sources, start, final)

        # 11. Retrieval-Log (JSONL)
        result = QueryResult(
            answer=final.answer,
            confidence=confidence,
            sources=sources,
            validation=final.validation,
            grounding=final.grounding,
            pii_redacted=final.pii_redacted,
        )
        self._log_retrieval(
            session_id=session_id,
            rewrite_result=rewrite_result,
            query_type=p.router.route(search_query),
            hits=hits,
            confidence=confidence,
            outcome=_outcome(confidence, result),
            answer_length=len(final.answer),
            timer=timer,
        )

        # 12. Audit (LAST)
        self._audit(query, result, session_id, rewrite_result)

    async def _retrieve_dedup(
        self,
        queries: list[str],
        filters: dict[str, Any] | None,
        timer: PipelineTimer | None = None,
    ) -> list[Any]:
        """Retrieval ueber alle Queries mit Deduplizierung."""
        all_hits: list[Any] = []
        for q in queries:
            hits = await self._pipeline.retriever.retrieve(
                q, filters=filters, timer=timer,
            )
            all_hits.extend(hits)
        return _deduplicate_hits(all_hits)

    def _audit(
        self,
        query: str,
        result: QueryResult,
        session_id: str,
        rewrite_result: RewriteResult | None = None,
    ) -> None:
        """Schreibt den Audit-Eintrag (immer letzter Schritt)."""
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        source_ids = [s.get("id", "") for s in result.sources]
        record: dict[str, Any] = {
            "query_hash": query_hash,
            "confidence": result.confidence,
            "source_ids": source_ids,
            "latency_ms": round(result.latency_ms, 1),
            "guardrail_blocked": result.guardrail_blocked,
            "smalltalk": result.smalltalk,
            "pii_redacted": result.pii_redacted,
            "grounding_score": (
                round(result.grounding.score, 3)
                if result.grounding is not None
                else None
            ),
            "session_id": session_id,
            "query_rewritten": (
                rewrite_result.was_rewritten if rewrite_result else False
            ),
        }
        self._pipeline.audit_logger.log(record)

    def _log_retrieval(
        self,
        *,
        session_id: str,
        rewrite_result: RewriteResult | None,
        query_type: str,
        hits: list[Any],
        confidence: str,
        outcome: str,
        answer_length: int,
        timer: PipelineTimer,
    ) -> None:
        """Schreibt JSONL-Retrieval-Log-Eintrag (fail-silent)."""
        if not self._pipeline.settings.retrieval_log_enabled:
            return
        entry = build_log_entry(
            session_id=session_id,
            query_original=rewrite_result.original if rewrite_result else "",
            query_rewritten=(
                rewrite_result.rewritten if rewrite_result else ""
            ),
            was_rewritten=(
                rewrite_result.was_rewritten if rewrite_result else False
            ),
            query_type=query_type,
            hits=hits,
            confidence=confidence,
            outcome=outcome,
            answer_length=answer_length,
            timer=timer,
        )
        self._pipeline.retrieval_logger.log(entry)

    def clear_session(self, session_id: str) -> None:
        """Loescht die Memory einer Session."""
        self._sessions.pop(session_id, None)


def _elapsed_ms(start: float) -> float:
    """Berechnet die vergangene Zeit in Millisekunden."""
    return (time.monotonic() - start) * 1000


def _outcome(confidence: str, result: QueryResult) -> str:
    """Bestimmt das Outcome fuer das Retrieval-Log."""
    if result.smalltalk:
        return "smalltalk"
    if result.guardrail_blocked:
        return "blocked"
    if confidence == "rot":
        return "refusal"
    return "answered"


def _done_event(
    confidence: str,
    sources: list[dict[str, Any]],
    start: float,
    final: _FinalizedAnswer | None = None,
) -> dict[str, Any]:
    """Baut das finale Done-SSE-Event.

    ``final_answer`` ist die autoritative (validierte, PII-redigierte)
    Antwort — Clients ersetzen damit den gestreamten Rohtext, falls er
    abweicht.
    """
    event: dict[str, Any] = {
        "type": "done",
        "confidence": confidence,
        "sources": sources,
        "latency_ms": round(_elapsed_ms(start), 1),
    }
    if final is None:
        return event
    event["final_answer"] = final.answer
    event["pii_redacted"] = final.pii_redacted
    if final.grounding is not None:
        event["grounding_score"] = round(final.grounding.score, 3)
        event["grounded"] = final.grounding.grounded
    if final.validation is not None:
        event["citations_valid"] = len(final.validation.citations_valid)
        event["citations_invalid"] = len(final.validation.citations_invalid)
        event["urls_removed"] = len(final.validation.urls_removed)
    return event


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


# Maximale Snippet-Laenge in der API-Antwort.
# Frontend hat ExpandableChunk mit "Mehr anzeigen" — daher grosszuegig.
_SNIPPET_MAX_CHARS = 2000


# Satzende: Punkt/Ausrufezeichen/Fragezeichen gefolgt von Whitespace
_SENTENCE_END_RE = re.compile(r"[.!?]\s")


def _truncate_snippet(text: str, max_chars: int = _SNIPPET_MAX_CHARS) -> str:
    """Kuerzt ein Snippet, bevorzugt am Satzende, mit Ellipse.

    Versucht zuerst, an einem Satzende innerhalb des Limits zu schneiden.
    Faellt auf Wortgrenze zurueck wenn kein Satzende im hinteren Drittel
    gefunden wird.
    """
    text = text.strip()
    if len(text) <= max_chars:
        return text
    # Suche letztes Satzende im erlaubten Bereich (mind. 60 % nutzen)
    min_cut = max_chars * 3 // 5
    best = -1
    for m in _SENTENCE_END_RE.finditer(text, 0, max_chars):
        if m.start() >= min_cut:
            best = m.start() + 1  # nach dem Satzzeichen
    if best > 0:
        return text[:best].rstrip()
    # Fallback: Wortgrenze
    cut = text.rfind(" ", 0, max_chars)
    if cut < max_chars // 2:
        cut = max_chars
    return text[:cut].rstrip() + " \u2026"


def _build_sources(hits: list[Any]) -> list[dict[str, Any]]:
    """Baut Source-Dicts aus RetrievalHits.

    Feldmenge MUSS mit ``api.schemas.Source`` uebereinstimmen
    (Vertrags-Test in test_api.py).
    """
    sources: list[dict[str, Any]] = []
    for i, hit in enumerate(hits, start=1):
        payload = getattr(hit, "payload", {}) or {}
        raw_text = payload.get("text_raw") or payload.get("text") or ""
        # Alle Facetten-Metadaten aus dem Qdrant-Payload durchreichen
        bereich = payload.get("bereich") or []
        if isinstance(bereich, str):
            bereich = [bereich]
        sources.append({
            "id": f"S{i}",
            "titel": payload.get("titel") or "Unbekannt",
            "url": payload.get("source_url"),
            "datei": payload.get("datei") or "",
            "snippet": _truncate_snippet(raw_text),
            "page": payload.get("page"),
            "score": round(hit.rerank_score, 4),
            "doc_type": payload.get("doc_type") or "",
            "breadcrumb": payload.get("breadcrumb") or "",
            "figure_refs": payload.get("figure_refs") or [],
            "figure_captions": payload.get("figure_captions") or [],
            "bereich": bereich,
            "herkunft": payload.get("herkunft") or "",
            "quelltyp": payload.get("quelltyp") or "",
            "vertraulichkeit": payload.get("vertraulichkeit") or "",
            "status": payload.get("status") or "",
            "jahr": payload.get("jahr"),
            "thema": payload.get("thema") or [],
            "anlage": payload.get("anlage") or [],
            "projekt": payload.get("projekt") or [],
            "ansprechperson": payload.get("ansprechperson") or [],
            "autor": payload.get("autor") or [],
            "grad": payload.get("grad") or "",
        })
    return sources


