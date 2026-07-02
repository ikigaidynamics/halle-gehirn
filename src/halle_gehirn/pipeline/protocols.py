"""Protocol-Interfaces für jede Pipeline-Stage.

Jede Stage im Stack implementiert genau eines dieser Protocols und ist damit
austauschbar, ohne andere Module zu berühren (Kernprinzip 2). `factory.py`
baut die Pipeline aus der Config, indem es je Protocol eine Implementierung wählt.

Hier stehen nur Signaturen + Docstrings — die Implementierungen entstehen
phasenweise (siehe TASKS.md). Konkrete Typen (ExtractedDoc, Chunk, RetrievalHit,
…) werden in den jeweiligen Modulen definiert; hier als `object`/Platzhalter
referenziert, um Zirkularimporte im Bootstrap zu vermeiden.
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class Extractor(Protocol):
    """Wandelt eine Quelle (PDF/DOCX/PPTX/XLSX/HTML/Bild) in ein strukturiertes
    Dokument (Markdown + Tabellen + Metadaten). Docling ist die Primär-Impl."""

    def extract(self, source: str) -> Any:
        """Extrahiert eine Quelle zu einem ExtractedDoc. Wirft bei Fehler."""
        ...


@runtime_checkable
class Chunker(Protocol):
    """Zerlegt ein Dokument struktur- und token-bewusst in Chunks."""

    def chunk(self, doc: Any) -> list[Any]:
        """Liefert Chunks mit Zeichen-Offsets und (falls vorhanden) Seitenzahl."""
        ...


@runtime_checkable
class ContextEnricher(Protocol):
    """Erzeugt pro Chunk einen knappen Kontextsatz (Contextual Retrieval) und
    stellt ihn vor dem Embedding voran."""

    async def enrich(self, chunks: list[Any], doc: Any) -> list[Any]:
        """Reichert Chunks um `context_prefix` an."""
        ...


@runtime_checkable
class DenseEmbedder(Protocol):
    """Erzeugt dichte Vektoren (Ollama qwen3-embedding, Matryoshka)."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Batched Embedding einer Textliste."""
        ...


@runtime_checkable
class SparseEmbedder(Protocol):
    """Erzeugt spärliche BM25-Vektoren (FastEmbed, deutsch gestemmt)."""

    def embed(self, texts: list[str]) -> list[Any]:
        """Liefert Sparse-Vektoren (Indizes + Werte)."""
        ...


@runtime_checkable
class Reranker(Protocol):
    """Sortiert Retrieval-Kandidaten nach Relevanz neu
    (Logprobs / Cross-Encoder / Cohere)."""

    async def rerank(self, query: str, hits: list[Any]) -> list[Any]:
        """Gibt die neu geordneten Treffer zurück."""
        ...


@runtime_checkable
class Retriever(Protocol):
    """High-Level-Retrieval: Hybrid-Query → MMR → Rerank → Top-K."""

    async def retrieve(self, query: str) -> list[Any]:
        """Liefert die finalen Top-K-Treffer für eine Anfrage."""
        ...


@runtime_checkable
class QueryTransformer(Protocol):
    """Transformiert die Anfrage (HyDE, Multi-Query, Decomposition)."""

    async def transform(self, query: str) -> list[str]:
        """Liefert eine oder mehrere transformierte Anfragen."""
        ...


@runtime_checkable
class Router(Protocol):
    """Klassifiziert den Anfrage-Typ und wählt die Retrieval-Strategie."""

    def route(self, query: str) -> str:
        """Liefert den Query-Typ (factual/vergleich/definition/temporal/overview)."""
        ...


@runtime_checkable
class Generator(Protocol):
    """Erzeugt die Antwort aus Anfrage + Kontext (streaming-fähig, qwen3)."""

    async def generate(self, query: str, context: list[Any]) -> AsyncIterator[str]:
        """Streamt die Antwort-Tokens."""
        ...


@runtime_checkable
class ConfidenceGate(Protocol):
    """Ampel-Gate: entscheidet grün/gelb(hedge)/rot(Refusal) anhand der Scores."""

    def assess(self, hits: list[Any]) -> str:
        """Liefert die Ampelstufe ('gruen'|'gelb'|'rot')."""
        ...


@runtime_checkable
class Validator(Protocol):
    """URL-Whitelist + Citation-Enforcement: entfernt erfundene Links,
    erzwingt Quellen-IDs je Aussage."""

    def validate(self, answer: str, sources: list[Any]) -> Any:
        """Liefert die validierte Antwort + Report."""
        ...


@runtime_checkable
class GroundingChecker(Protocol):
    """Faithfulness/NLI-Check: verifiziert die Antwort gegen den Kontext."""

    async def check(self, answer: str, context: list[Any]) -> Any:
        """Flaggt nicht gestützte Sätze."""
        ...


@runtime_checkable
class Guardrail(Protocol):
    """Input-Sanitization, Prompt-Injection-Abwehr (inkl. indirekt),
    Topic-Gate, Output-PII-Filter."""

    def check(self, text: str) -> Any:
        """Liefert Freigabe oder Blockade + Grund."""
        ...


@runtime_checkable
class AuditLogger(Protocol):
    """Append-only-Audit: wer/Frage/genutzte Quellen/Konfidenz/Zeit (DSGVO)."""

    def log(self, record: dict[str, Any]) -> None:
        """Schreibt einen Audit-Eintrag."""
        ...
