"""Zentrale Konfiguration für Halle-Gehirn.

Liest `.env` (via pydantic-settings) und exportiert alle Variablen aus
CLAUDE.md Kap. 6 als typisierte Felder mit Defaults. Einzige Quelle der
Wahrheit für Laufzeit-Konfiguration — keine hardcodierten Werte anderswo.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Alle Laufzeit-Parameter, aus `.env` überschreibbar."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ── LLM & Embedding (lokal, Ollama) ──
    ollama_url: str = "http://localhost:11434"
    ollama_urls: str = ""  # Komma-separierte Fallback-URLs (UI-waehlbar)
    llm_model: str = "qwen3:14b"
    embedding_model: str = "qwen3-embedding:0.6b"
    embedding_dim: int = 1024
    sparse_model: str = "Qdrant/bm25"
    sparse_language: str = "german"
    use_colbert: bool = False

    # ── Retrieval / Hybrid ──
    top_k_initial: int = 20
    top_k_final: int = 5
    fusion: Literal["rrf", "dbsf"] = "rrf"
    use_mmr: bool = True
    mmr_lambda: float = 0.7
    reranker: Literal["logprobs", "cross_encoder", "cohere"] = "logprobs"
    rerank_num_predict: int = 8  # Ja/Nein braucht nur 1 Token
    rerank_top_logprobs: int = 5
    use_query_transform: bool = False
    use_router: bool = True

    # ── Confidence-Gate ──
    conf_green: float = 0.7
    conf_yellow: float = 0.4

    # ── Indexierung ──
    use_contextual_retrieval: bool = True
    chunk_target_tokens: int = 512
    chunk_max_tokens: int = 768
    min_chunk_chars: int = 100
    filter_source_code: bool = True
    context_concurrency: int = 4

    # ── Extraction (Docling) ──
    docling_ocr: bool = True
    docling_table_mode: Literal["fast", "accurate"] = "accurate"
    docling_do_figures: bool = True
    figures_dir: str = "data/figures"

    # ── Generierung ──
    streaming: bool = True
    gen_num_predict: int = 2048  # Grosszuegig: think-Block + sichtbare Antwort
    gen_temperature: float = 0.3
    memory_window: int = 5
    use_summary_memory: bool = True
    use_grounding_check: bool = True
    grounding_threshold: float = 0.5

    # ── Qdrant ──
    qdrant_url: str = "http://localhost:6335"
    qdrant_collection: str = "halle_wissen"
    qdrant_quantization: str = "int8"

    # ── Compliance / Governance ──
    audit_log: bool = True
    on_prem: bool = True
    contact_fallback_url: str = (
        "https://www.b-tu.de/fg-automatisierungstechnik/team/kontakt"
    )

    # ── Observability ──
    log_level: str = "INFO"
    otel_enabled: bool = True

    # ── Crawler (sekundär) ──
    crawler_domains: str = "b-tu.de"
    crawler_rate_limit: float = 1.0
    crawler_max_pages: int = 2000

    # ── API ──
    api_port: int = 8001
    api_base_url: str = ""  # leer → wird aus api_port abgeleitet
    admin_api_key: str = "change-me-in-production"
    cors_origins: str = "http://localhost:8501,http://localhost:3000"
    rate_limit_rpm: int = 60

    # ── Halle-Gehirn / Branding ──
    bot_name: str = "Jarvis"
    primary_color: str = "#000000"  # TODO: BTU-Hausfarbe
    language: str = "de"

    @model_validator(mode="after")
    def _derive_api_base_url(self) -> Settings:
        """Leitet api_base_url aus api_port ab, wenn nicht explizit gesetzt."""
        if not self.api_base_url:
            self.api_base_url = f"http://localhost:{self.api_port}"
        return self


@lru_cache
def get_settings() -> Settings:
    """Gecachte Settings-Instanz (einzige Instanziierungsstelle)."""
    return Settings()
