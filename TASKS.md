# TASKS.md — Halle-Gehirn

Backlog je Phase. `[x]` erledigt · `[ ]` offen. Reihenfolge des ersten Builds:
0 → 1 → 2 → 3 → 4 → 5 → 6 → 8 → 9 → 7 → 10.

## Phase 0 — Bootstrap  ✅
- [x] Verzeichnisstruktur + Package-Inits
- [x] `pyproject.toml` (hatchling, Python 3.12) + Dependencies
- [x] `config.py` (pydantic-settings, alle .env-Variablen typisiert)
- [x] `.env.example`
- [x] `pipeline/protocols.py` (alle Stage-Interfaces)
- [x] `vector_store/schema.py` (Qdrant-Hybrid + **Taxonomie**: Enums, ChunkPayload, Indizes)
- [x] `data/vokabular.yaml` + `data/manifest.yaml` (Vorlage) + `docs/taxonomie.md`
- [x] `ruff.toml` + `mypy.ini` + `observability/logging_config.py`
- [x] `PLANNING.md` + `TASKS.md` + `README.md` + `.gitignore`
- [x] `pip install -e ".[dev]"` lauffähig · `ruff check` + `mypy` grün auf den Stubs

## Phase 1 — Extraction (Docling) + Crawler
- [x] `extraction/base.py` (Extractor-Protocol + ExtractedDoc + TableBlock)
- [x] `extraction/docling_extractor.py` (PRIMÄR — DoclingExtractor)
- [x] `extraction/{html_extractor,boilerplate,title_extractor,manual_loader}.py`
- [x] `scraper/{fetcher,js_fetcher}.py` (sekundär, Delta + Playwright)
- [x] `ruff check` + `mypy` grün auf allen Phase-1-Modulen (70 source files)
- [x] Tests: Docling-Extraktion, Boilerplate, Delta (16 tests, alle gruen)

## Phase 2 — Indexierung  ✅
- [x] `pipeline/sentence_splitter.py` (deutsch, Abkürzungs-Schutz)
- [x] `pipeline/chunker.py` (MarkdownChunker: Heading-Sections + Satz-Split + tiktoken)
- [x] `pipeline/context_enricher.py` (Contextual Retrieval via Ollama)
- [x] `embeddings/{provider,ollama_embedder,sparse_embedder,colbert_embedder}.py`
- [x] `pipeline/ingest.py` — **liest `data/manifest.yaml`, validiert Slugs gegen `vokabular.yaml`**
- [x] `src/scripts/reindex.py`
- [x] `ruff check` + `mypy` grün auf 70 source files
- [x] Tests: Splitter (10), Chunker (9), Ingest (16) — 35 Tests, alle gruen
- [x] End-to-End-Verifikation: Test-PDF → 3 Chunks, ChunkPayload komplett, Sparse BM25 OK, Fail-Fast OK

## Phase 3 — Vector-Store (Qdrant Hybrid)  ✅
- [x] `vector_store/qdrant_client.py` (Factory, upsert, hybrid_query, snapshot, erasure, delete_by_source_hash)
- [x] `src/scripts/snapshot.py` (create/list CLI)
- [x] `src/scripts/reindex.py` verdrahtet: --reset loescht/erstellt NUR QDRANT_COLLECTION
- [x] Tests: Collection (4), Upsert+Retrieve (5), Hybrid-Query fusioniert (3), Erasure (2), Filter (3) — 17 Tests, alle gruen
- [x] End-to-End-Verifikation: Test-PDF → Embed → Upsert halle_wissen → Hybrid-Query (RRF, 3 Treffer mit Scores) → --reset beweist: nur halle_wissen angefasst, cottbus_buergerservice + btu_transfer unberuehrt

## Phase 4 — Retrieval  ✅
- [x] `embeddings/reranker.py` (Logprobs-Reranker, Ollama-basiert)
- [x] `retrieval/{query_transform,router,retriever}.py` (HybridRetriever, KeywordRouter, OllamaQueryTransformer)
- [x] `pipeline/stages/confidence.py` (Ampel: gruen/gelb/rot)
- [x] Tests: Hybrid+Rerank, Confidence-Schwellen, Router (test_retrieval.py, alle gruen)
- [x] End-to-End-Verifikation: Live-Query mit Reranking + Confidence-Gate

## Phase 5 — Generierung  ✅
- [x] `generator/{ollama_client,prompts,smalltalk,memory}.py` (Persona: Jarvis, SSE-Streaming, Think-Tag-Filterung)
- [x] `pipeline/stages/{validation,grounding,guardrails}.py` (URL-Whitelist, Faithfulness, Prompt-Injection-Abwehr, PII-Redaktion)
- [x] Tests: Refusal, Citation-Pflicht, Prompt-Injection, Smalltalk (test_generation.py, alle gruen)
- [x] End-to-End-Verifikation: Live-Generierung mit Streaming + Grounding-Check

## Phase 6 — API  ✅
- [x] `pipeline/{factory,orchestrator}.py` (QueryPipeline, QueryOrchestrator mit 10-Stage-Pipeline)
- [x] `api/{schemas,main, routes/{chat,health,admin}}.py` (FastAPI, CORS, Rate-Limit, SSE)
- [x] `governance/audit.py` (StructlogAuditLogger)
- [x] `ui/streamlit_app.py` (Chat-UI mit SSE-Streaming, Konfidenz-Ampel, Quellen)
- [x] Tests: /chat(/stream), /ready, Admin-Auth (test_api.py + test_orchestrator.py, 19 Tests gruen)
- [x] Live-Verifikation: /health=ok, /ready=ready (Qdrant+Ollama true), Admin 401/200, Chat JSON + SSE-Streaming mit Quellen + Citations

## Phase 8 — Evaluation  (vorgezogen)
- [ ] `data/eval/golden_qa.yaml` + `eval/{golden_qa,metrics,runner}.py`
- [ ] `src/scripts/eval_queries.py` → Baseline-Report
- [ ] Regression-Gate (CI)
- [x] `eval/chunk_quality.py` (ChunkQualityReport: Token-Verteilung, Fragmente,
      Heading-/Zeichen-Abdeckung, Tabellen-Integritaet) + `tests/test_chunk_quality.py`
      (Invarianten + Qualitaetsbaender) + `scripts/eval_chunk_quality.py` (Report)
- [x] **DEFEKT behoben (WP1):** Tabellen fallen nicht mehr unter den positionalen
      Tail-/Front-Matter-Drop (`chunk_filter.py`: is_table-Ausnahme); ehem.
      xfail `test_content_tables_survive_tail_matter` ist jetzt regulaerer Test.
- [x] **WP1 — BTU-Masterarbeiten sauber chunken** (siehe
      `docs/audit_2026-07_zwischenstand.md`): Kurzfassung/Abstract ueberleben
      den Front-Matter-Filter (`_ABSTRACT_HEADINGS`-Whitelist) · Heading-Ketten
      top→leaf in `split_sections` (mehrstufige Breadcrumbs) · Eval-Korpus um
      Kurzfassung + Unterkapitel erweitert (70 Chunk-Tests gruen).
- [x] **WP2 — Ingester sauber (Contextual Retrieval + Delta):**
      Enricher in `run_ingest` verdrahtet (3 Phasen: Prepare → Enrich →
      Payloads; graceful bei Ollama-Ausfall; Tabellen werden mit angereichert) ·
      `build_doc_summary` bevorzugt Kurzfassung/Abstract fuer den Kontext-Prompt ·
      Manifest-Titel ueberschreibt doc.title auch im Ingest-Pfad ·
      `delete_stale_chunks` (alte Hashes + ueberzaehlige Indizes, Aufruf NACH
      Upsert) · `--delta`-Flag in reindex.py (skip via source_hash,
      `docs_unchanged` in IngestStats) · 14 neue Tests (gemockter Ollama/Qdrant).
- [ ] Zwischenaudit-Arbeitspakete WP3–WP7: siehe
      `docs/audit_2026-07_zwischenstand.md` (WP5 Streaming-Security →
      WP3 Seiten-Provenienz → WP6 API/Frontend → WP4 Titelblatt-Parser →
      WP7 Ops).

## Phase 9 — Compliance & Security  (vorgezogen)
- [ ] `governance/{audit,consent,erasure}.py`
- [ ] Prompt-Injection-/Jailbreak-Suite in Eval-Regression
- [ ] `docs/`: AVV-Template, TOMs, Model-Card, EU-AI-Act-Art.-4-Checkliste

## Phase 7 — Frontend (Demonstrator-Widget)
- [ ] `frontend/widget/` (Preact+Tailwind, <100 KB, Streaming, Quellen, Konfidenz)
- [ ] Branding: **Jarvis**, `PRIMARY_COLOR` (BTU-Hausfarbe)

## Phase 10 — Deployment & Observability
- [ ] `docker-compose.yml`, `Caddyfile`, `ecosystem.config.js`
- [ ] `observability/tracing.py` (OTEL), Prometheus/Grafana, Backup

## Nach dem Spine — Geschwister-Module (siehe PLANNING.md)
- [ ] `norm_store/` — deterministischer Norm-Store
- [ ] `live_data/` — OPC-UA-Snapshot-Reader (anlage-Slugs = API-Geräte-IDs)
- [ ] `agent/` — Perceive-Judge-Report-Loop + Bestätigen/Verwerfen-Eval
