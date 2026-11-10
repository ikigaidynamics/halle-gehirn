"""Baut Query-Pipeline aus config -- Phase 6.

Instanziiert alle Pipeline-Komponenten und gibt sie als
typisiertes QueryPipeline-Objekt zurueck. Einzige Stelle,
an der Implementierungen an Protocols gebunden werden.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.generator.ollama_client import OllamaGenerator
from halle_gehirn.generator.openai_client import OpenAIGenerator
from halle_gehirn.governance.audit import StructlogAuditLogger
from halle_gehirn.observability.retrieval_logger import RetrievalJsonlLogger
from halle_gehirn.pipeline.stages.confidence import ConfidenceGate
from halle_gehirn.pipeline.stages.grounding import FaithfulnessChecker
from halle_gehirn.pipeline.stages.guardrails import PromptGuardrail
from halle_gehirn.pipeline.stages.validation import CitationValidator
from halle_gehirn.retrieval.query_rewriter import QueryRewriter
from halle_gehirn.retrieval.query_transform import OllamaQueryTransformer
from halle_gehirn.retrieval.retriever import HybridRetriever
from halle_gehirn.retrieval.router import KeywordRouter

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class QueryPipeline:
    """Haelt alle instanziierten Pipeline-Komponenten.

    Frozen: Komponenten werden einmal gebaut und nicht veraendert.
    ConversationMemory ist per-Session und wird vom Orchestrator
    verwaltet -- nicht Teil der Pipeline.
    """

    retriever: HybridRetriever
    router: KeywordRouter
    query_rewriter: QueryRewriter
    query_transformer: OllamaQueryTransformer
    generator: OllamaGenerator | OpenAIGenerator
    confidence_gate: ConfidenceGate
    guardrail: PromptGuardrail
    validator: CitationValidator
    grounding_checker: FaithfulnessChecker
    audit_logger: StructlogAuditLogger
    retrieval_logger: RetrievalJsonlLogger
    settings: Settings


def build_query_pipeline(
    settings: Settings | None = None,
) -> QueryPipeline:
    """Baut die Query-Pipeline aus der Config.

    Instanziiert alle Komponenten mit geteilter Settings-Instanz.
    Jede Komponente wird genau einmal erzeugt.

    Args:
        settings: Optionale Settings (Default: get_settings()).

    Returns:
        QueryPipeline mit allen Komponenten.
    """
    s = settings or get_settings()
    router = KeywordRouter(settings=s)

    # Generator basierend auf Backend-Wahl
    if s.llm_backend == "openai":
        generator: OllamaGenerator | OpenAIGenerator = OpenAIGenerator(settings=s)
        logger.info("using_openai_backend", base_url=s.openai_base_url)
    else:
        generator = OllamaGenerator(settings=s)
        logger.info("using_ollama_backend", url=s.ollama_url)

    pipeline = QueryPipeline(
        retriever=HybridRetriever(settings=s, router=router),
        router=router,
        query_rewriter=QueryRewriter(settings=s),
        query_transformer=OllamaQueryTransformer(settings=s),
        generator=generator,
        confidence_gate=ConfidenceGate(settings=s),
        guardrail=PromptGuardrail(),
        validator=CitationValidator(),
        grounding_checker=FaithfulnessChecker(settings=s),
        audit_logger=StructlogAuditLogger(),
        retrieval_logger=RetrievalJsonlLogger(
            log_dir=Path(s.retrieval_log_dir),
        ),
        settings=s,
    )
    logger.info("query_pipeline_built")
    return pipeline
