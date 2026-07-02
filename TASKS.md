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

## Phase 2 — Indexierung
- [ ] `pipeline/sentence_splitter.py` (deutsch, Abkürzungs-Schutz)
- [ ] `pipeline/chunker.py` (Docling HybridChunker + Refine)
- [ ] `pipeline/context_enricher.py` (Contextual Retrieval)
- [ ] `embeddings/{provider,ollama_embedder,sparse_embedder,colbert_embedder}.py`
- [ ] `pipeline/ingest.py` — **liest `data/manifest.yaml`, validiert Slugs gegen `vokabular.yaml`**
- [ ] `src/scripts/reindex.py`
- [ ] Tests: Chunk-Längen, Splitter, deterministische IDs, Manifest→Payload

## Phase 3 — Vector-Store (Qdrant Hybrid)
- [ ] `vector_store/qdrant_client.py` (Factory, upsert, hybrid_query, snapshot, erasure)
- [ ] `src/scripts/snapshot.py`
- [ ] Tests: Collection, Upsert+Retrieve, Hybrid-Query fusioniert

## Phase 4 — Retrieval
- [ ] `embeddings/reranker.py` (logprobs/cross_encoder)
- [ ] `retrieval/{query_transform,router,retriever}.py`
- [ ] `pipeline/stages/confidence.py` (Ampel)
- [ ] Tests: Hybrid+Rerank, Confidence-Schwellen, Router

## Phase 5 — Generierung
- [ ] `generator/{ollama_client,prompts,smalltalk,memory}.py` (Persona: Jarvis)
- [ ] `pipeline/stages/{validation,grounding,guardrails}.py`
- [ ] Tests: Refusal, Citation-Pflicht, Prompt-Injection, Smalltalk

## Phase 6 — API
- [ ] `pipeline/{factory,orchestrator}.py`
- [ ] `api/{schemas,main, routes/{chat,health,admin}}.py`
- [ ] Tests: /chat(/stream), /ready, Admin-Auth

## Phase 8 — Evaluation  (vorgezogen)
- [ ] `data/eval/golden_qa.yaml` + `eval/{golden_qa,metrics,runner}.py`
- [ ] `src/scripts/eval_queries.py` → Baseline-Report
- [ ] Regression-Gate (CI)

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
