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

    # ── LLM & Embedding ──
    llm_backend: Literal["ollama", "openai"] = "ollama"
    # Ollama-Einstellungen
    ollama_url: str = "http://localhost:11434"
    ollama_urls: str = ""  # Komma-separierte Fallback-URLs (UI-waehlbar)
    llm_model: str = "qwen3:14b"
    # OpenAI-kompatibles Backend (vLLM, text-generation-inference, etc.)
    openai_base_url: str = ""  # z.B. http://141.43.76.22:8080/v1 (GPU-Host)
    openai_api_key: str = ""  # leer fuer lokale Server ohne Auth
    openai_model: str = ""  # Modellname fuer OpenAI-API
    # Embedding-Backend: ollama, fastembed (lokal) oder openai (OpenAI-kompatible API)
    embedding_backend: Literal["ollama", "fastembed", "openai"] = "ollama"
    embedding_model: str = "qwen3-embedding:0.6b"  # Modellname fuer Ollama/OpenAI
    fastembed_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dim: int = 1024
    # OpenAI-kompatibles Embedding-Backend (z.B. vLLM, TEI, llama.cpp)
    embedding_openai_base_url: str = ""  # z.B. http://141.43.76.22:8081/v1
    embedding_openai_api_key: str = ""  # leer fuer lokale Server ohne Auth
    embedding_openai_model: str = ""  # Modellname fuer OpenAI-API (leer = embedding_model)
    sparse_model: str = "Qdrant/bm25"
    sparse_language: str = "german"
    use_colbert: bool = False

    # ── Retrieval / Hybrid ──
    top_k_initial: int = 20
    top_k_final: int = 5
    fusion: Literal["rrf", "dbsf"] = "rrf"
    use_mmr: bool = True
    mmr_lambda: float = 0.7
    reranker: Literal["logprobs", "cross_encoder", "cohere", "none"] = "logprobs"
    rerank_num_predict: int = 8  # Ja/Nein braucht nur 1 Token
    rerank_top_logprobs: int = 5
    use_query_rewrite: bool = True
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
    max_filter_ratio: float = 0.80  # Notbremse: Filter deaktiviert wenn er mehr als 80% verwerfen wuerde
    context_concurrency: int = 4
    chunks_per_page_warn: float = 5.0  # Warnung ab N Chunks/Seite
    chunks_per_page_abort: float = 15.0  # Harter Abbruch ab N Chunks/Seite

    # ── Extraction (Docling) ──
    docling_serve_url: str = ""  # leer = lokale Lib; z.B. http://141.43.76.21:5001
    docling_ocr: bool = True
    docling_table_mode: Literal["fast", "accurate"] = "accurate"
    docling_do_figures: bool = True
    figures_dir: str = "data/figures"
    boilerplate_clean: bool = True  # Kopf-/Fusszeilen + Seitenzahlen entfernen

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
    retrieval_log_enabled: bool = True
    retrieval_log_dir: str = "logs/retrieval"

    # ── Crawler (sekundär) ──
    crawler_domains: str = "b-tu.de"
    crawler_rate_limit: float = 1.0
    crawler_max_pages: int = 2000

    # ── API ──
    api_port: int = 8001
    # Statische Frontend-Builds (Standalone-Bundle): Pfad mit Unterordnern
    # ``chat/`` und ``admin/`` (vite build). Leer = aus (Dev-Modus nutzt
    # Vite-Dev-Server auf 3000/3001).
    static_dir: str = ""
    # Standalone-Bundle: Chat-URL beim Start im Standardbrowser oeffnen
    # (nur im Bundle-Entry Point wirksam). Dev-Default aus.
    open_browser: bool = False
    api_base_url: str = ""  # leer → wird aus api_port abgeleitet
    admin_api_key: str = "change-me-in-production"
    cors_origins: str = "http://localhost:3000,http://localhost:3001"
    rate_limit_rpm: int = 60

    # ── UI-Ports ──
    chat_ui_port: int = 3000  # Preact-Widget (Vite dev-server)
    ingest_ui_port: int = 3001  # Wissensbestand-Frontend (Streamlit)

    # ── Halle-Gehirn / Branding ──
    bot_name: str = "KI Fabrik Scout"
    primary_color: str = "#c41230"  # MDZ-Rot (per .env ueberschreibbar)
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
